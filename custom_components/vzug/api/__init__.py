import asyncio
import dataclasses
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict, cast
import json_repair

import httpx
from yarl import URL

from . import discovery  # noqa: F401 # type: ignore

_LOGGER = logging.getLogger(__name__)

DeviceStatusInactiveT = Literal["true"] | Literal["false"]


class DeviceStatusProgramEnd(TypedDict, total=False):
    EndType: str
    End: str


class DeviceStatus(TypedDict, total=False):
    DeviceName: str
    Serial: str
    Inactive: DeviceStatusInactiveT
    Program: str
    Status: str
    ProgramEnd: DeviceStatusProgramEnd
    deviceUuid: str


class UpdateProgress(TypedDict, total=False):
    download: int
    installation: int


class UpdateComponent(TypedDict, total=False):
    name: str
    running: bool
    available: bool
    required: bool
    progress: UpdateProgress


class UpdateStatus(TypedDict, total=False):
    status: Literal["idle"] | str
    isAIUpdateAvailable: bool
    isHHGUpdateAvailable: bool
    isSynced: bool
    components: list[UpdateComponent]


class PushNotification(TypedDict, total=False):
    date: str
    message: str


class Command(TypedDict, total=False):
    type: (
        Literal["action"]
        | Literal["boolean"]
        | Literal["selection"]
        | Literal["status"]
        | Literal["range"]
    )
    description: str
    command: str
    value: str
    alterable: bool
    options: list[str]
    minMax: tuple[str, str]
    refresh: list[str]
    """list of commands to refresh when this command is changed"""


HhFwVersion = TypedDict(
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


class AiFwVersion(TypedDict, total=False):
    fn: str
    SW: str
    SD: str
    HW: str
    apiVersion: str
    phy: str
    deviceUuid: str


class EcoInfoMetric(TypedDict, total=False):
    total: float
    average: float
    program: float
    option: float  # sent by adorawash for water, no idea what it is


class DoorOpeningPeriod(TypedDict, total=False):
    duration: int
    amount: int


class EcoInfo(TypedDict, total=False):
    water: EcoInfoMetric
    energy: EcoInfoMetric
    doorOpenings: dict[str, dict[str, DoorOpeningPeriod]]


class Category(TypedDict, total=False):
    description: str


class DeviceInfo(TypedDict, total=False):
    model: str
    description: str
    """model description"""
    type: Literal["WA"] | str
    name: str
    serialNumber: str
    articleNumber: str
    """the serial number starts with this"""
    apiVersion: str  # seen: 1.5.0 / 1.7.0 / 1.8.0
    zhMode: int


class ProgramOptionA(TypedDict, total=False):
    min: int
    max: int
    step: int


class ProgramOptionB(TypedDict, total=False):
    set: bool
    options: list[Any]


class ProgramOption(ProgramOptionA, ProgramOptionB): ...


class ProgramInfo(TypedDict, total=False):
    id: int
    name: str
    status: Literal["selected"] | str
    stepIds: list[int]


@dataclasses.dataclass(slots=True, kw_only=True)
class Program:
    info: ProgramInfo
    options: dict[str, ProgramOption]

    @classmethod
    def build(cls, raw: dict[str, Any]) -> "Program":
        info = {}
        options = raw.copy()
        for key in ProgramInfo.__required_keys__ | ProgramInfo.__optional_keys__:
            # extract all ProgramInfo keys from 'options' to 'info'
            try:
                info[key] = options[key]
            except LookupError:
                pass
            else:
                del options[key]
        return Program(info=cast(ProgramInfo, info), options=options)


class ZoneTemp(TypedDict, total=False):
    set: float
    act: float
    min: float
    max: float


class ZoneProgram(TypedDict, total=False):
    id: int
    status: str
    temp: ZoneTemp
    doorClosed: bool
    zone: str
    light: dict[str, Any]
    preheatStatus: dict[str, Any]
    probeInserted: dict[str, Any]
    superCool: dict[str, int]
    superFreeze: dict[str, int]
    partyCooling: dict[str, int]


class HhDeviceStatus(TypedDict, total=False):
    errors: list[dict[str, Any]]
    displayedErrors: list[dict[str, Any]]
    notifications: list[dict[str, Any]]
    isUpdatePossible: bool


class CloudStatus(TypedDict, total=False):
    enabled: bool
    claimed: bool
    status: str
    secTokenValid: bool
    scope: str
    telemetryCollectionEnabled: bool


@dataclasses.dataclass(slots=True, kw_only=True)
class AggProgramState:
    zones: list[ZoneProgram]


@dataclasses.dataclass(slots=True, kw_only=True)
class AggState:
    zh_mode: int
    device: DeviceStatus
    device_fetched_at: datetime = dataclasses.field(compare=False)
    notifications: list[PushNotification]
    eco_info: EcoInfo
    hh_device_status: HhDeviceStatus

    def to_cache(self) -> dict:
        return {
            "zh_mode": self.zh_mode,
            "device": dict(self.device),
            "device_fetched_at": self.device_fetched_at.isoformat(),
            "notifications": [dict(n) for n in self.notifications],
            "eco_info": dict(self.eco_info),
            "hh_device_status": dict(self.hh_device_status),
        }

    @classmethod
    def from_cache(cls, data: dict) -> "AggState":
        return cls(
            zh_mode=data["zh_mode"],
            device=DeviceStatus(**data["device"]),
            device_fetched_at=datetime.fromisoformat(data["device_fetched_at"]),
            notifications=[PushNotification(**n) for n in data["notifications"]],
            eco_info=EcoInfo(**data["eco_info"]),
            hh_device_status=HhDeviceStatus(**data["hh_device_status"]),
        )


@dataclasses.dataclass(slots=True, kw_only=True)
class AggUpdateStatus:
    update: UpdateStatus
    ai_fw_version: AiFwVersion
    hh_fw_version: HhFwVersion

    def to_cache(self) -> dict:
        return {
            "update": dict(self.update),
            "ai_fw_version": dict(self.ai_fw_version),
            "hh_fw_version": dict(self.hh_fw_version),
        }

    @classmethod
    def from_cache(cls, data: dict) -> "AggUpdateStatus":
        return cls(
            update=UpdateStatus(**data["update"]),
            ai_fw_version=AiFwVersion(**data["ai_fw_version"]),
            hh_fw_version=HhFwVersion(**data["hh_fw_version"]),
        )


@dataclasses.dataclass(slots=True, kw_only=True)
class AggMeta:
    mac_address: str
    model_id: str
    model_name: str
    device_name: str
    serial_number: str
    api_version: tuple[int, ...]
    ai_api_version: tuple[int, ...]

    def create_name(self) -> str:
        if name := self.device_name.strip():
            return name
        return self.model_name or self.model_id or self.serial_number

    def create_unique_name(self) -> str:
        name = self.create_name()
        if self.serial_number in name:
            return name
        return f"{name} ({self.serial_number})"

    def supports_update_status(self) -> bool:
        return self.ai_api_version >= (1, 7, 0)


@dataclasses.dataclass(slots=True, kw_only=True)
class AggCategory:
    key: str
    description: str
    commands: dict[str, Command]


AggConfig = dict[str, AggCategory]


def agg_config_to_cache(config: AggConfig) -> dict:
    return {
        key: {
            "key": cat.key,
            "description": cat.description,
            "commands": {ck: dict(cv) for ck, cv in cat.commands.items()},
        }
        for key, cat in config.items()
    }


def agg_config_from_cache(data: dict) -> AggConfig:
    return {
        key: AggCategory(
            key=cat["key"],
            description=cat["description"],
            commands={ck: Command(**cv) for ck, cv in cat["commands"].items()},
        )
        for key, cat in data.items()
    }


@dataclasses.dataclass(kw_only=True, slots=True)
class Credentials:
    username: str
    password: str


class VZugApi:
    @property
    def base_url(self) -> URL:
        return self._base_url

    def __init__(
        self,
        base_url: URL | str,
        *,
        client: httpx.AsyncClient,
    ) -> None:
        self._client = client
        self._base_url = URL(base_url)

    async def _command(
        self,
        component: str,
        *,
        command: str,
        params: dict[str, str] | None = None,
        raw: bool = False,
        expected_type: Any = None,
        reject_empty: bool = False,
        attempts: int = 3,
        retry_delay: float = 1.0,
        value_on_err: Callable[[], Any] | None = None,
    ) -> Any:
        if params is None:
            params = {}
        final_params = params.copy()
        final_params["command"] = command
        final_params["_"] = str(int(time.time()))

        url = str(self._base_url / component)

        async def once() -> Any:
            _LOGGER.debug(
                "running command %s %s on %s @ %s",
                command,
                params,
                component,
                self._base_url,
            )
            resp = await self._client.get(url, params=final_params)
            resp.raise_for_status()

            if raw:
                content = resp.text
                _LOGGER.debug("raw response: %s", content)
                return content

            try:
                data = resp.json()
            except ValueError:
                if resp.content:
                    _LOGGER.debug("invalid json payload: %s", resp.content)
                    # Try to repair the JSON response before giving up
                    try:
                        repaired_json = json_repair.repair_json(resp.text)
                        data = json.loads(repaired_json)
                        _LOGGER.debug("successfully repaired json: %s", data)
                    except Exception as repair_error:
                        _LOGGER.debug("json repair failed: %s", repair_error)
                        raise  # Re-raise the original ValueError
                else:
                    # we got an empty response, we just treat this as 'None'
                    data = None

            _LOGGER.debug("data: %s", data)
            if expected_type is list and data is None:
                # if we want a list and the response is null, we just treat that as an empty list
                data: Any = []

            if expected_type is not None:
                assert isinstance(data, expected_type), (
                    f"data type mismatch ({type(data)} != {expected_type})"
                )
            if reject_empty:
                assert len(data) > 0, "empty response rejected"
            return data

        last_exc = ValueError("no attempts made")
        attempt_idx = 0
        while attempt_idx < attempts:
            # starts with 0s, then retry_delay
            await asyncio.sleep(attempt_idx * retry_delay)

            try:
                return await once()
            except httpx.HTTPStatusError as err:
                if err.response.status_code == httpx.codes.UNAUTHORIZED:
                    raise AuthenticationFailed from err
                if not err.response.is_server_error:
                    raise

                last_exc = err
                _LOGGER.debug("server error: %s", err.response)
            except httpx.TransportError as err:
                last_exc = err
                _LOGGER.debug("transport error: %r", err)
                continue
            except AssertionError as exc:
                last_exc = exc
                _LOGGER.debug("response data assertion failed: %s", exc)
            except Exception as exc:
                last_exc = exc
                _LOGGER.debug("unknown error: %r", exc)

            attempt_idx += 1

        if value_on_err:
            _LOGGER.exception("command error, using default", exc_info=last_exc)
            return value_on_err()

        raise last_exc

    async def aggregate_state(self, *, default_on_error: bool = True) -> AggState:
        # always start with zh_mode, that seems to do something??
        # zh_mode = await self.get_zh_mode(default_on_error=True)
        zh_mode = -1

        async def _device() -> tuple[DeviceStatus, datetime]:
            data = await self.get_device_status(default_on_error=default_on_error)
            return data, datetime.now(UTC)

        (
            (device, device_fetched_at),
            notifications,
            eco_info,
            hh_device_status,
        ) = await asyncio.gather(
            _device(),
            self.get_last_push_notifications(default_on_error=default_on_error),
            self.get_eco_info(default_on_error=default_on_error),
            self.get_hh_device_status(default_on_error=default_on_error),
        )

        return AggState(
            zh_mode=zh_mode,
            device=device,
            device_fetched_at=device_fetched_at,
            notifications=notifications,
            eco_info=eco_info,
            hh_device_status=hh_device_status,
        )

    async def aggregate_update_status(
        self, *, supports_update_status: bool, default_on_error: bool = True
    ) -> AggUpdateStatus:
        async def _update() -> UpdateStatus:
            if supports_update_status:
                return await self.get_update_status(default_on_error=default_on_error)
            return UpdateStatus()

        update, ai_fw_version, hh_fw_version = await asyncio.gather(
            _update(),
            self.get_ai_fw_version(default_on_error=default_on_error),
            self.get_hh_fw_version(default_on_error=default_on_error),
        )
        return AggUpdateStatus(
            update=update,
            ai_fw_version=ai_fw_version,
            hh_fw_version=hh_fw_version,
        )

    async def aggregate_meta(self, *, default_on_error: bool = False) -> AggMeta:
        # First method used in config flow to get details about the device
        (
            mac_address,
            device_status,
            model_description,
            ai_firmware,
        ) = await asyncio.gather(
            # This is all from the AI Module/API
            self.get_mac_address(default_on_error=default_on_error),
            self.get_device_status(default_on_error=default_on_error),
            self.get_model_description(default_on_error=default_on_error),
            self.get_ai_fw_version(default_on_error=default_on_error),
        )

        try:
            # Only supported on some devices, probably with newer hh module
            device_info = await self.get_device_info(default_on_error=True)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == httpx.codes.NOT_FOUND:
                # Device does not support this, so we just use the AI data
                device_info = None
            else:
                raise

        raw_ai_api_version = ai_firmware.get("apiVersion", "")
        ai_api_version = tuple(map(int, raw_ai_api_version.split(".")))

        if device_info:
            raw_api_version = device_info.get("apiVersion", "")
            hh_api_version = tuple(map(int, (raw_api_version.split("."))))

            return AggMeta(
                mac_address=mac_address,
                model_id=device_info.get("model", ""),
                model_name=device_info.get("description", ""),
                device_name=device_info.get("name", ""),
                serial_number=device_info.get("serialNumber", ""),
                api_version=hh_api_version,
                ai_api_version=ai_api_version,
            )
        else:
            return AggMeta(
                mac_address=mac_address,
                model_id="",
                model_name=model_description,
                device_name=device_status.get("DeviceName", ""),
                serial_number=device_status.get("Serial", ""),
                api_version=ai_api_version,
                ai_api_version=ai_api_version,
            )

    async def aggregate_config(self) -> AggConfig:
        category_keys = await self.list_categories()

        async def _fetch_category(
            category_key: str,
        ) -> tuple[str, AggCategory]:
            category_raw, command_keys = await asyncio.gather(
                self.get_category(category_key),
                self.list_commands(category_key),
            )
            commands: dict[str, Command] = {}

            async def _fetch_command(command_key: str) -> None:
                commands[command_key] = await self.get_command(command_key)

            await asyncio.gather(
                *(_fetch_command(ck) for ck in command_keys)
            )
            return category_key, AggCategory(
                key=category_key,
                description=category_raw.get("description", ""),
                commands=commands,
            )

        results = await asyncio.gather(
            *(_fetch_category(k) for k in category_keys)
        )
        return {key: cat for key, cat in results}

    async def get_mac_address(self, *, default_on_error: bool = False) -> str:
        return await self._command(
            "ai",
            command="getMacAddress",
            raw=True,
            value_on_err=(lambda: "") if default_on_error else None,
        )

    async def get_model_description(self, *, default_on_error: bool = False) -> str:
        return await self._command(
            "ai",
            command="getModelDescription",
            raw=True,
            value_on_err=(lambda: "") if default_on_error else None,
        )

    async def get_device_status(
        self, *, default_on_error: bool = False
    ) -> DeviceStatus:
        return await self._command(
            "ai",
            command="getDeviceStatus",
            expected_type=dict,
            value_on_err=(lambda: DeviceStatus()) if default_on_error else None,
        )

    async def get_update_status(
        self, *, default_on_error: bool = False
    ) -> UpdateStatus:
        return await self._command(
            "ai",
            command="getUpdateStatus",
            expected_type=dict,
            value_on_err=(lambda: UpdateStatus()) if default_on_error else None,
        )

    async def check_for_updates(self) -> None:
        await self._command(
            "ai",
            command="checkUpdate",
            raw=True,
            attempts=2,
        )

    async def do_ai_update(self) -> None:
        await self._command("ai", command="doAIUpdate")

    async def do_hhg_update(self) -> None:
        await self._command("ai", command="doHHGUpdate")

    async def get_last_push_notifications(
        self, *, default_on_error: bool = False
    ) -> list[PushNotification]:
        return await self._command(
            "ai",
            command="getLastPUSHNotifications",
            expected_type=list,
            value_on_err=(lambda: []) if default_on_error else None,
        )

    async def list_categories(self) -> list[str]:
        return await self._command(
            "hh",
            command="getCategories",
            expected_type=list,
            # the API sometimes wrongly returns an empty list, but there are also appliances (ex. AdoraWash V4000) which don't have any categories
            reject_empty=False,
        )

    async def get_category(self, value: str) -> Category:
        return await self._command(
            "hh", command="getCategory", params={"value": value}, expected_type=dict
        )

    async def list_commands(self, value: str) -> list[str]:
        return await self._command(
            "hh", command="getCommands", params={"value": value}, expected_type=list
        )

    async def get_command(self, value: str) -> Command:
        return await self._command(
            "hh", command="getCommand", params={"value": value}, expected_type=dict
        )

    async def set_command(self, command: str, value: str) -> None:
        await self._command(
            "hh",
            command=f"set{command}",
            params={"value": value},
            raw=True,
            attempts=2,
        )

    async def do_command_action(self, command: str) -> None:
        await self._command(
            "hh",
            command=f"do{command}",
            raw=True,
            attempts=2,
        )

    async def get_hh_fw_version(self, *, default_on_error: bool = False) -> HhFwVersion:
        return await self._command(
            "hh",
            command="getFWVersion",
            expected_type=dict,
            value_on_err=(lambda: HhFwVersion()) if default_on_error else None,
        )

    async def get_ai_fw_version(self, *, default_on_error: bool = False) -> AiFwVersion:
        return await self._command(
            "ai",
            command="getFWVersion",
            expected_type=dict,
            value_on_err=(lambda: AiFwVersion()) if default_on_error else None,
        )

    async def get_zh_mode(self, *, default_on_error: bool = False) -> int:
        data = await self._command(
            "hh",
            command="getZHMode",
            expected_type=dict,
            value_on_err=(lambda: {"value": -1}) if default_on_error else None,
        )
        return data["value"]

    async def get_eco_info(self, *, default_on_error: bool = False) -> EcoInfo:
        result = await self._command(
            "hh",
            command="getEcoInfo",
            expected_type=dict,
            value_on_err=(lambda: EcoInfo()) if default_on_error else None,
        )

        water_total = result.get("water", {}).get("total", 0)
        energy_total = result.get("energy", {}).get("total", 0)

        # If both water and energy totals are 0, and there are no doorOpenings,
        # we return an empty EcoInfo.
        # This is to handle cases where the API returns 0s for both metrics
        if water_total == 0 and energy_total == 0 and "doorOpenings" not in result:
            return EcoInfo()

        return result

    async def get_device_info(self, *, default_on_error: bool = False) -> DeviceInfo:
        # 'getAPIVersion' can be used to get only the API version
        # 'getZHMode' gives just the zh mode
        return await self._command(
            "hh",
            command="getDeviceInfo",
            expected_type=dict,
            value_on_err=(lambda: DeviceInfo()) if default_on_error else None,
        )

    async def get_hh_device_status(
        self, *, default_on_error: bool = False
    ) -> HhDeviceStatus:
        return await self._command(
            "hh",
            command="getDeviceStatus",
            expected_type=dict,
            value_on_err=(lambda: HhDeviceStatus()) if default_on_error else None,
        )

    async def get_cloud_status(
        self, *, default_on_error: bool = False
    ) -> CloudStatus:
        return await self._command(
            "ai",
            command="getCloudStatus",
            expected_type=dict,
            value_on_err=(lambda: CloudStatus()) if default_on_error else None,
        )

    async def get_program(self) -> list[dict[str, Any]]:
        return await self._command(
            "hh",
            command="getProgram",
            expected_type=list,
        )

    async def aggregate_program(
        self, *, default_on_error: bool = False
    ) -> AggProgramState:
        raw_programs = await self._command(
            "hh",
            command="getProgram",
            expected_type=list,
            value_on_err=(lambda: []) if default_on_error else None,
        )
        zones: list[ZoneProgram] = [
            cast(ZoneProgram, z)
            for z in raw_programs
            if "zone" in z
        ]
        return AggProgramState(zones=zones)

    async def set_program(
        self, program_id: int, options: dict[str, Any] | None = None
    ) -> list[Any]:
        # example options: {"id":50,"dryPlus":false,"energySaving":false,"partialload":false,"rinsePlus":false,"steamfinish":true}
        # also seen with just the "id" key
        if not options:
            options = {}
        options["id"] = program_id
        return await self._command(
            "hh",
            command="setProgram",
            params={"value": json.dumps(options)},
            raw=True,
            attempts=2,
        )

    async def get_all_program_ids(self) -> list[int]:
        return await self._command(
            "hh",
            command="getAllProgramIds",
            expected_type=list,
        )

    async def get_program_list(self) -> dict[int, str]:
        """Get selectable program IDs and resolve their names.

        Only programs in _SELECTABLE_PROGRAM_IDS are included.
        This limits program selection to device types where setProgram
        is confirmed to work (currently dishwashers).
        """
        program_ids = await self.get_all_program_ids()
        return {
            pid: PROGRAM_NAMES[pid]
            for pid in program_ids
            if pid in _SELECTABLE_PROGRAM_IDS
        }


# Program ID → human-readable name mapping.
# Sourced from the V-ZUG app's EasyCook database (extracted.js asset paths).
# The device API does NOT return program names; the official app resolves
# them client-side from an embedded database.
PROGRAM_NAMES: dict[int, str] = {
    # ── Oven (BO) ──
    3: "Hold Temperature",
    4: "Hot Air",
    5: "Hot Air Humid",
    7: "PizzaPlus",
    8: "Top/Bottom Heat",
    9: "Top/Bottom Heat Humid",
    10: "Bottom Heat",
    11: "Grill",
    12: "Grill Forced Convection",
    48: "Hot Air Eco",
    49: "Top/Bottom Heat Eco",
    101: "Plate Warmer",
    # ── Dishwasher (GS) ──
    50: "Eco",
    51: "Automatic",
    52: "Daily Quick",
    53: "Sprint",
    54: "Intensive",
    55: "Silent",
    56: "Party",
    57: "Glass",
    58: "Fondue/Raclette",
    59: "Hygiene",
    60: "Machine Care",
    61: "Pre-Rinsing",
    86: "Short",
    87: "Intensive Plus",
    88: "Rinse Plus",
    89: "Wine Degu",
    90: "Plate Heat Up",
    91: "Synthetic",
    92: "Toy",
    93: "Beer Glass",
    94: "Wine Glass",
    95: "Grease Filter",
}

# Program IDs where setProgram is confirmed to work.
# Only dishwasher (GS) programs — the V-ZUG app marks most other device
# types as sendProgramSupported=false (including the BO Combair V600,
# WA AdoraWash V2000, and WT AdoraDry V2000).
_SELECTABLE_PROGRAM_IDS = frozenset(
    pid for pid in PROGRAM_NAMES if 50 <= pid <= 95
)

# German device firmware text → English translation.
# The device API returns status strings in the appliance's display language.
# There is no API to change it; these are best-effort client-side translations.
DEVICE_TEXT_DE_EN: dict[str, str] = {
    # Common device status strings
    "Keine Betriebsart": "No Operating Mode",
    "Normalbetrieb": "Normal Operation",
    # Oven (BO) program names (from V-ZUG product documentation)
    "Heissluft": "Hot Air",
    "Heissluft feucht": "Hot Air Humid",
    "Ober-/Unterhitze": "Top/Bottom Heat",
    "Ober-/Unterhitze feucht": "Top/Bottom Heat Humid",
    "Unterhitze": "Bottom Heat",
    "Umluftgrillen": "Grill Forced Convection",
    "Warmhalten": "Hold Temperature",
    "Heissluft Eco": "Hot Air Eco",
    "Ober-/Unterhitze Eco": "Top/Bottom Heat Eco",
    "Tellerwärmer": "Plate Warmer",
}

# German status field prefix translations (for regex-based replacement).
_STATUS_TRANSLATIONS_DE_EN: dict[str, str] = {
    "Temperatureinstellung": "Temperature",
}


def translate_device_text(text: str) -> str:
    """Translate known German device firmware text to English.

    Returns the original text if no translation is found.
    """
    return DEVICE_TEXT_DE_EN.get(text, text)


def translate_status_text(text: str) -> str:
    """Translate known German status field patterns to English."""
    for de, en in _STATUS_TRANSLATIONS_DE_EN.items():
        if de in text:
            text = text.replace(de, en)
    return text


class AuthenticationFailed(Exception): ...
