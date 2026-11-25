"""A simulated V-ZUG appliance for tests that run a real Home Assistant.

It answers the '/ai' and '/hh' requests of the integration from the recorded
responses in 'tests/fixtures/<device>/responses', the same files the Flask emulator
in 'tests/fixtures/start_single_emulator.py' serves. Instead of a socket it plugs
into httpx as a transport, so tests need no network and no running emulator.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parent / "fixtures"
DEVICES = sorted(
    path.name for path in FIXTURES.iterdir() if (path / "responses").is_dir()
)

_AI_FILES = {
    "getDeviceStatus": "ai_get_devicestatus.json",
    "getFWVersion": "ai_get_fwversion.json",
    "getLastPUSHNotifications": "ai_get_lastpushnotifications.json",
    "getMacAddress": "ai_get_macaddress.txt",
    "getModelDescription": "ai_get_modeldescription.txt",
    "getUpdateStatus": "ai_get_updatestatus.json",
}
_HH_FILES = {
    "getAllProgramIds": "hh_get_allprogramids.json",
    "getProgram": "hh_get_getprogram.json",
    "getDeviceInfo": "hh_get_deviceinfo.json",
    "getEcoInfo": "hh_get_ecoinfo.json",
    "getFWVersion": "hh_get_fwversion.json",
    "getZHMode": "hh_get_zhmode.json",
}
# commands that change something, the appliance answers them with an empty 200
_WRITE_PREFIXES = ("set", "do", "check")

Override = Callable[[str | None], httpx.Response] | httpx.Response | Exception

REALM = "vzug-test"
NONCE = "dcd98b7102dd2f0e8b11d0f600bfb0c093"


@dataclass
class Call:
    component: str
    command: str
    value: str | None


@dataclass
class FakeAppliance:
    """One appliance, addressed by its host name."""

    device: str
    host: str
    username: str | None = None
    password: str | None = None
    calls: list[Call] = field(default_factory=list)
    overrides: dict[tuple[str, str], Override] = field(default_factory=dict)
    reachable: bool = True

    @property
    def base_url(self) -> str:
        return f"http://{self.host}"

    @property
    def responses(self) -> Path:
        return FIXTURES / self.device / "responses"

    @property
    def mac_address(self) -> str:
        return (self.responses / "ai_get_macaddress.txt").read_text().strip()

    def response_json(self, filename: str) -> Any:
        return json.loads((self.responses / filename).read_text())

    def set_response(self, component: str, command: str, value: Override) -> None:
        """Answer 'command' with 'value' from now on (a response, a function or an
        exception to raise)."""
        self.overrides[(component, command)] = value

    def set_json(self, component: str, command: str, data: Any) -> None:
        self.set_response(component, command, httpx.Response(200, json=data))

    def commands(self, component: str | None = None) -> list[str]:
        return [
            call.command
            for call in self.calls
            if component is None or call.component == component
        ]

    def writes(self) -> list[Call]:
        return [call for call in self.calls if call.command.startswith(_WRITE_PREFIXES)]

    # request handling

    def handle(self, request: httpx.Request) -> httpx.Response:
        if not self.reachable:
            raise httpx.ConnectError("appliance unreachable", request=request)
        if self.password is not None and not self._authorized(request):
            return httpx.Response(
                401,
                headers={
                    "WWW-Authenticate": f'Digest realm="{REALM}", qop="auth", '
                    f'nonce="{NONCE}", algorithm=MD5'
                },
            )

        component = request.url.path.strip("/")
        command = request.url.params.get("command", "")
        value = request.url.params.get("value")
        self.calls.append(Call(component, command, value))

        if (override := self.overrides.get((component, command))) is not None:
            if isinstance(override, Exception):
                raise override
            if isinstance(override, httpx.Response):
                return override
            return override(value)

        if component == "ai":
            return self._answer_ai(command)
        if component == "hh":
            return self._answer_hh(command, value)
        return httpx.Response(404)

    def _answer_ai(self, command: str) -> httpx.Response:
        if filename := _AI_FILES.get(command):
            return self._file(filename)
        if command.startswith(_WRITE_PREFIXES):
            return httpx.Response(200, text="")
        return self._file("ai_get_invalid_command.txt", status=404)

    def _answer_hh(self, command: str, value: str | None) -> httpx.Response:
        if command in ("getCategories", "getCategory", "getCommands"):
            categories = self.response_json("hh_get_categories.json")
            if command == "getCategories":
                return httpx.Response(200, json=[c["id"] for c in categories])
            for category in categories:
                if category["id"] == value:
                    key = "category" if command == "getCategory" else "commands"
                    return httpx.Response(200, json=category[key])
            return httpx.Response(400, json={"error": ["code", "400.03"]})
        if command == "getCommand":
            for details in self.response_json("hh_get_command_details.json"):
                if details["id"] == value:
                    return httpx.Response(200, json=details["details"])
            return httpx.Response(400, json={"error": ["code", "400.03"]})
        if filename := _HH_FILES.get(command):
            return self._file(filename)
        if command.startswith(_WRITE_PREFIXES):
            return httpx.Response(200, text="")
        return self._file("hh_get_invalid_command.txt", status=404)

    def _file(self, filename: str, *, status: int = 200) -> httpx.Response:
        path = self.responses / filename
        if not path.exists():
            return httpx.Response(400, json={"error": '{ "code":400.03}'})
        content = path.read_text().strip()
        if '"code": 404' in content or '"code":404' in content:
            status = 404
        return httpx.Response(status, text=content)

    def _authorized(self, request: httpx.Request) -> bool:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Digest "):
            return False
        parts = dict(re.findall(r'(\w+)="?([^",]+)"?', header[len("Digest ") :]))
        if parts.get("username") != self.username:
            return False
        ha1 = _md5(f"{self.username}:{REALM}:{self.password}")
        ha2 = _md5(f"{request.method}:{parts.get('uri', '')}")
        expected = _md5(
            f"{ha1}:{parts.get('nonce')}:{parts.get('nc')}:{parts.get('cnonce')}"
            f":{parts.get('qop')}:{ha2}"
        )
        return parts.get("response") == expected


def _md5(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()  # noqa: S324


class ApplianceNetwork:
    """All simulated appliances of a test, routed by host name."""

    def __init__(self) -> None:
        self.appliances: dict[str, FakeAppliance] = {}

    def add(
        self,
        device: str,
        *,
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> FakeAppliance:
        appliance = FakeAppliance(
            device=device,
            host=host or f"{device.replace('_', '-')}.local",
            username=username,
            password=password,
        )
        self.appliances[appliance.host] = appliance
        return appliance

    def handle(self, request: httpx.Request) -> httpx.Response:
        appliance = self.appliances.get(request.url.host)
        if appliance is None:
            raise httpx.ConnectError(f"no appliance at {request.url.host}")
        return appliance.handle(request)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)
