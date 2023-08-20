import asyncio
import time
import typing

import aiohttp
import yarl

DeviceStatusInactiveT = typing.Literal["true"] | typing.Literal["false"]


class DeviceStatusProgramEnd(typing.TypedDict):
    EndType: str
    End: str


class DeviceStatus(typing.TypedDict):
    DeviceName: str
    Serial: str
    Inactive: DeviceStatusInactiveT
    Program: str
    Status: str
    ProgramEnd: DeviceStatusProgramEnd
    deviceUuid: str


class UpdateProgress(typing.TypedDict):
    download: int
    installation: int


class UpdateComponent(typing.TypedDict):
    name: str
    running: bool
    available: bool
    required: bool
    progress: UpdateProgress


class UpdateStatus(typing.TypedDict):
    status: str
    isAIUpdateAvailable: bool
    isHHGUpdateAvailable: bool
    isSynced: bool
    components: list[UpdateComponent]


class PushNotification(typing.TypedDict):
    date: str
    message: str


class CommandValue(typing.TypedDict):
    type: str
    description: str
    command: str
    value: str
    alterable: bool


HhFwVersion = typing.TypedDict(
    "HhFwVersion",
    {
        "fn": str,
        "an": str,
        "v": str,
        "vr01": str,
        "v2": str,
        "vr10": str,
        "vi2": str,
        "vh1": str,
        "vh2": str,
        "vr0B": str,
        "vp": str,
        "vr0C": str,
        "vr0E": str,
        "Mh": str,
        "MD": str,
        "Zh": str,
        "ZV": str,
        "ZHSW": str,
        "device-type": str,
    },
    total=False,
)


class AiFwVersion(typing.TypedDict, total=False):
    fn: str
    SW: str
    SD: str
    HW: str
    apiVersion: str
    phy: str
    deviceUuid: str


class VZugApi:
    _session: aiohttp.ClientSession
    _base_url: yarl.URL

    @property
    def base_url(self) -> yarl.URL:
        return self._base_url

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: yarl.URL | str,
    ) -> None:
        self._session = session
        self._base_url = yarl.URL(base_url)

    async def _command(
        self,
        component: str,
        *,
        command: str,
        params: dict[str, str] | None = None,
        raw: bool = False,
        expected_type: typing.Any = None,
        attempts: int = 5,
        retry_delay: float = 2.0
    ) -> typing.Any:
        if params is None:
            params = {}
        params["command"] = command
        params["_"] = str(int(time.time()))

        url = self._base_url / component

        async def once() -> typing.Any:
            async with self._session.get(url, params=params) as resp:
                resp.raise_for_status()

                if raw:
                    return await resp.text()

                data = await resp.json(content_type=None)
                if expected_type is not None:
                    assert isinstance(data, expected_type)
                return data

        last_exc = ValueError("no attempts made")
        for _ in range(attempts):
            try:
                return await once()
            except aiohttp.ClientError as exc:
                last_exc = exc
            await asyncio.sleep(retry_delay)

        raise last_exc

    async def get_mac_address(self) -> str:
        return await self._command("ai", command="getMacAddress", raw=True)

    async def get_model_description(self) -> str:
        return await self._command("ai", command="getModelDescription", raw=True)

    async def get_device_status(self) -> DeviceStatus:
        return await self._command("ai", command="getDeviceStatus", expected_type=dict)

    async def get_update_status(self) -> UpdateStatus:
        return await self._command("ai", command="getUpdateStatus", expected_type=dict)

    async def do_ai_update(self) -> None:
        await self._command("ai", command="doAIUpdate")

    async def do_hhg_update(self) -> None:
        await self._command("ai", command="doHHGUpdate")

    async def get_last_push_notifications(self) -> list[PushNotification]:
        return await self._command(
            "ai", command="getLastPUSHNotifications", expected_type=list
        )

    async def list_categories(self) -> list[str]:
        return await self._command("hh", command="getCategories", expected_type=list)

    async def list_commands(self, value: str) -> list[str]:
        return await self._command(
            "hh", command="getCommands", params={"value": value}, expected_type=list
        )

    async def get_command(self, value: str) -> CommandValue:
        return await self._command(
            "hh", command="getCommand", params={"value": value}, expected_type=dict
        )

    async def get_hh_fw_version(self) -> HhFwVersion:
        return await self._command("hh", command="getFWVersion", expected_type=dict)

    async def get_ai_fw_version(self) -> AiFwVersion:
        return await self._command("ai", command="getFWVersion", expected_type=dict)
