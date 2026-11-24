import asyncio
import dataclasses
import json
import logging
import time
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict, cast
import json_repair

import httpx
from yarl import URL

from . import discovery  # noqa: F401 # type: ignore

_LOGGER = logging.getLogger(__name__)

# how many consecutive failures it takes before we accept that an appliance doesn't
# know 'getZHMode'. These devices fail a request every now and then, so a single
# error is not enough to write the command off.
ZH_MODE_WARMUP_MAX_FAILURES = 3

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
    lastMonth: float
    lastYear: float


class EcoInfo(TypedDict, total=False):
    water: EcoInfoMetric
    energy: EcoInfoMetric
    doorOpenings: list[dict[str, Any]]
    """refrigerators, ex. [{"today":{"duration":12,"amount":3},
    "sevenDayAverage":{...},"thirtyDayAverage":{...}}]"""


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


@dataclasses.dataclass(slots=True, kw_only=True)
class AggState:
    zh_mode: int
    device: DeviceStatus
    device_fetched_at: datetime
    notifications: list[PushNotification]
    eco_info: EcoInfo
    errors: list[str] = dataclasses.field(default_factory=list)
    """codes the appliance shows on its display, '/hh getDeviceStatus' (hh 1.5)"""


@dataclasses.dataclass(slots=True, kw_only=True)
class AggUpdateStatus:
    update: UpdateStatus
    ai_fw_version: AiFwVersion
    hh_fw_version: HhFwVersion
    cloud_status: dict[str, Any] = dataclasses.field(default_factory=dict)
    """'/ai getCloudStatus' (ai 1.6), ex. {"enabled":true,"status":"connected"}"""


@dataclasses.dataclass(slots=True, kw_only=True)
class AggMeta:
    mac_address: str
    model_id: str
    model_name: str
    device_name: str
    serial_number: str
    api_version: tuple[int, ...]
    ai_api_version: tuple[int, ...] | None = None
    """from '/ai getAPIVersion', None if the appliance doesn't answer it"""
    hh_api_version: tuple[int, ...] | None = None
    """from '/hh getAPIVersion', else 'getDeviceInfo', None if neither answers"""
    machine_type: str = ""
    """'getDeviceInfo' type: GS dishwasher, WA washer, BO oven, GK hob, KS fridge..."""

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
        return self.api_version >= (1, 7, 0)

    def supports_cloud_status(self) -> bool:
        return self.ai_api_version is not None and self.ai_api_version >= (1, 6, 0)


@dataclasses.dataclass(slots=True, kw_only=True)
class AggCategory:
    key: str
    description: str
    commands: dict[str, Command]


AggConfig = dict[str, AggCategory]


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
        credentials: Credentials | None = None,
    ) -> None:
        self._auth = (
            httpx.DigestAuth(
                username=credentials.username, password=credentials.password
            )
            if credentials
            else None
        )
        self._client = self._create_client()
        # only one request at a time may be inside the client, see '_get'
        self._request_lock = asyncio.Lock()
        self._base_url = URL(base_url)
        # consecutive warm-up failures, see ZH_MODE_WARMUP_MAX_FAILURES
        self._zh_mode_warmup_failures = 0
        # set once we learn that this appliance really doesn't have any categories
        self._categories_may_be_empty = False
        # the hh API version, learned in 'aggregate_meta'. Older versions need other
        # commands for the same thing. None = unknown, assume a current appliance.
        self.hh_api_version: tuple[int, ...] | None = None
        # 'getDeviceInfo' type, learned in 'aggregate_meta'
        self.machine_type = ""

    def hh_supports(self, version: tuple[int, ...]) -> bool:
        """Whether the hh API is at least 'version' (or unknown)."""
        return self.hh_api_version is None or self.hh_api_version >= version

    def _create_client(self) -> httpx.AsyncClient:
        transport = httpx.AsyncHTTPTransport(
            verify=False,
            # The appliances can't handle concurrent requests reliably: an AdoraWash
            # V6000 answers 'getCommand' with '400.03' far more often when several
            # requests run at the same time. A 4xx isn't retried, so a single such
            # answer fails the whole config refresh. One connection at a time.
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            retries=5,
        )
        return httpx.AsyncClient(auth=self._auth, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str) -> httpx.Response:
        # Requests must not queue up inside httpcore's connection pool. If a request
        # gives up waiting there (pool timeout or cancellation) in the same moment
        # the pool hands it a freshly created connection, that connection is never
        # used and never released. With a single connection the pool is then stuck
        # for good and every later request fails with 'PoolTimeout' (#165). With
        # this lock there is never more than one request in the pool, so it can't
        # happen. It costs nothing since we only allow one connection anyway.
        async with self._request_lock:
            try:
                return await self._client.get(url)
            except httpx.PoolTimeout:
                # nobody else is in the pool, so it is broken. Start over with a
                # fresh client instead of failing until Home Assistant restarts.
                _LOGGER.warning("connection pool is stuck, recreating the http client")
                old_client, self._client = self._client, self._create_client()
                await old_client.aclose()
                raise

    async def _command(
        self,
        component: str,
        *,
        command: str,
        params: dict[str, str] | None = None,
        raw: bool = False,
        expected_type: Any = None,
        reject_empty: bool = False,
        attempts: int = 5,
        retry_delay: float = 2.0,
        value_on_err: Callable[[], Any] | None = None,
        value_on_client_err: Callable[[], Any] | None = None,
    ) -> Any:
        if params is None:
            params = {}

        # Some appliances are strict about query formatting. Mirror web UI shape:
        # command first, value second, cache-buster in milliseconds, and spaces as %20.
        final_params: dict[str, str] = {"command": command}
        final_params.update(params)
        final_params["_"] = str(int(time.time() * 1000))
        query = urllib.parse.urlencode(final_params, quote_via=urllib.parse.quote)

        url = str(self._base_url / component)
        request_url = f"{url}?{query}"

        async def once() -> Any:
            _LOGGER.debug(
                "running command %s %s on %s @ %s",
                command,
                params,
                component,
                self._base_url,
            )
            resp = await self._get(request_url)
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
            if isinstance(data, dict) and "error" in data:
                # some appliances report unsupported commands and transient failures
                # with a json error body and HTTP 200. Without this the body would
                # satisfy the type check below and get stored as if it were valid.
                raise ValueError(f"device returned an error response: {data['error']}")

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
                    if fallback := value_on_err or value_on_client_err:
                        # a client error (e.g. 404 "unknown command") won't go away by
                        # retrying, but the caller told us what to use instead. Without
                        # this, an optional command takes down the whole state update.
                        _LOGGER.debug(
                            "client error %s for %s, using default",
                            err.response.status_code,
                            command,
                        )
                        return fallback()
                    raise

                last_exc = err
                _LOGGER.debug("server error: %s", err.response)
            except httpx.TransportError as err:
                last_exc = err
                _LOGGER.debug("transport error: %r", err)
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

    async def aggregate_state(
        self,
        *,
        default_on_error: bool = True,
        include_device: bool = True,
        include_eco: bool = True,
    ) -> AggState:
        """Fetch the appliance state.

        'getDeviceStatus' wakes the appliance up, 'getLastPUSHNotifications' is
        answered by the AI module without touching it. Skipping the former lets the
        caller keep an eye on the appliance without disturbing it; the skipped
        values come back empty and are the caller's to carry over.
        """
        zh_mode = -1
        # the warm-up only exists to keep 'getEcoInfo' from returning zeros, so
        # there is no point in paying for it when we don't ask for eco info
        if include_eco and self._zh_mode_warmup_failures < ZH_MODE_WARMUP_MAX_FAILURES:
            # a cheap 'hh' command before the state poll keeps 'getEcoInfo' from
            # returning zeroed data on some appliances (ex. AdoraWash V6000).
            # Appliances which don't know the command (ex. Adora SLQ) answer with an
            # error - but so does a healthy one every now and then, so only give up
            # after it has failed several times in a row.
            try:
                zh_mode = await self.get_zh_mode(attempts=1)
            except Exception as exc:
                self._zh_mode_warmup_failures += 1
                _LOGGER.debug(
                    "zh_mode warm-up failed (%s/%s): %r",
                    self._zh_mode_warmup_failures,
                    ZH_MODE_WARMUP_MAX_FAILURES,
                    exc,
                )
            else:
                self._zh_mode_warmup_failures = 0

        async def _device() -> tuple[DeviceStatus, datetime]:
            if not include_device:
                return DeviceStatus(), datetime.now(UTC)
            data = await self.get_device_status(default_on_error=default_on_error)
            return data, datetime.now(UTC)

        async def _errors() -> list[str]:
            if not include_device or not self.hh_supports((1, 5, 0)):
                return []
            return await self.get_errors()

        async def _eco() -> EcoInfo:
            if not include_eco:
                return EcoInfo()
            return await self.get_eco_info(default_on_error=default_on_error)

        (
            (device, device_fetched_at),
            notifications,
            eco_info,
            errors,
        ) = await asyncio.gather(
            _device(),
            self.get_last_push_notifications(default_on_error=default_on_error),
            _eco(),
            _errors(),
        )

        return AggState(
            zh_mode=zh_mode,
            device=device,
            device_fetched_at=device_fetched_at,
            notifications=notifications,
            eco_info=eco_info,
            errors=errors,
        )

    async def aggregate_update_status(
        self,
        *,
        supports_update_status: bool,
        supports_cloud_status: bool = False,
        default_on_error: bool = True,
    ) -> AggUpdateStatus:
        async def _update() -> UpdateStatus:
            if supports_update_status:
                return await self.get_update_status(default_on_error=default_on_error)
            return UpdateStatus()

        async def _cloud() -> dict[str, Any]:
            if not supports_cloud_status:
                return {}
            return await self._command(
                "ai",
                command="getCloudStatus",
                expected_type=dict,
                attempts=2,
                value_on_err=dict,
            )

        update, ai_fw_version, hh_fw_version, cloud_status = await asyncio.gather(
            _update(),
            self.get_ai_fw_version(default_on_error=default_on_error),
            self.get_hh_fw_version(default_on_error=default_on_error),
            _cloud(),
        )
        return AggUpdateStatus(
            update=update,
            ai_fw_version=ai_fw_version,
            hh_fw_version=hh_fw_version,
            cloud_status=cloud_status,
        )

    async def aggregate_meta(
        self, *, default_on_error: bool = False, attempts: int = 5
    ) -> AggMeta:
        # First method used in config flow to get details about the device
        async def ai_details() -> tuple[str, DeviceStatus, str, AiFwVersion]:
            return await asyncio.gather(
                # This is all from the AI Module/API
                self.get_mac_address(
                    default_on_error=default_on_error, attempts=attempts
                ),
                self.get_device_status(
                    default_on_error=default_on_error, attempts=attempts
                ),
                self.get_model_description(
                    default_on_error=default_on_error, attempts=attempts
                ),
                self.get_ai_fw_version(
                    default_on_error=default_on_error, attempts=attempts
                ),
            )

        try:
            details = await ai_details()
        except httpx.HTTPStatusError as exc:
            if not exc.response.is_server_error:
                raise
            # some appliances (ex. AdoraWash V2000) answer 'getDeviceStatus' with a
            # 503 until something has talked to the 'hh' module
            _LOGGER.debug("server error during setup, waking the appliance: %r", exc)
            try:
                await self.get_zh_mode(attempts=1)
            except Exception as wake_exc:
                _LOGGER.debug("wake-up failed: %r", wake_exc)
                raise exc from None
            details = await ai_details()
        mac_address, device_status, model_description, ai_firmware = details

        ai_api_version, hh_api_version = await asyncio.gather(
            self.get_api_version("ai"), self.get_api_version("hh")
        )

        try:
            # Only supported on some devices, probably with newer hh module.
            # 'attempts' is deliberately not passed on: the appliance has answered by
            # now, and a single failure here would silently switch to the AI data.
            device_info = await self.get_device_info(default_on_error=True)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == httpx.codes.NOT_FOUND:
                # Device does not support this, so we just use the AI data
                device_info = None
            else:
                raise

        if device_info:
            info_api_version = parse_version(device_info.get("apiVersion")) or ()
            meta = AggMeta(
                mac_address=mac_address,
                model_id=device_info.get("model", ""),
                model_name=device_info.get("description", ""),
                device_name=device_info.get("name", ""),
                serial_number=device_info.get("serialNumber", ""),
                api_version=info_api_version,
                ai_api_version=ai_api_version,
                hh_api_version=hh_api_version or info_api_version or None,
                machine_type=device_info.get("type", ""),
            )
        else:
            meta = AggMeta(
                mac_address=mac_address,
                model_id="",
                model_name=model_description,
                device_name=device_status.get("DeviceName", ""),
                serial_number=device_status.get("Serial", ""),
                api_version=parse_version(ai_firmware.get("apiVersion")) or (),
                ai_api_version=ai_api_version,
                # 'getDeviceInfo' arrived with hh 1.3, so an appliance that knows
                # neither it nor 'getAPIVersion' is an old 1.0 - 1.2 one
                hh_api_version=hh_api_version or (1, 0, 0),
            )
        self.hh_api_version = meta.hh_api_version
        self.machine_type = meta.machine_type
        return meta

    async def aggregate_config(self) -> AggConfig:
        category_keys = await self.list_categories()
        if not category_keys and not self._categories_may_be_empty:
            # some appliances wrongly return an empty list when the hh module is
            # busy, others (ex. AdoraWash V4000) really don't have any categories.
            # Retry a couple of times, then believe the appliance and stop retrying.
            for delay in (1.0, 2.0):
                _LOGGER.debug("getCategories returned empty, retrying in %ss", delay)
                await asyncio.sleep(delay)
                category_keys = await self.list_categories()
                if category_keys:
                    break
        self._categories_may_be_empty = not category_keys

        config_tree: AggConfig = {}
        for category_key in category_keys:
            category_raw, command_keys = await asyncio.gather(
                self.get_category(category_key),
                self.list_commands(category_key),
            )
            category = AggCategory(
                key=category_key,
                description=category_raw.get("description", ""),
                commands={},
            )

            async def handle_command_key(command_key: str) -> None:
                try:
                    command_raw = await self.get_command(command_key)
                except httpx.HTTPStatusError as exc:
                    if not exc.response.is_client_error:
                        raise
                    # some appliances list commands they then refuse to read (ex.
                    # 'ecomXstatXtotalXclear' on an AdoraWash V6000 in standby)
                    _LOGGER.debug(
                        "skipping command %s: client error %s",
                        command_key,
                        exc.response.status_code,
                    )
                    return
                category.commands[command_key] = command_raw

            await asyncio.gather(
                *(handle_command_key(command_key) for command_key in command_keys)
            )
            config_tree[category_key] = category

        if self.machine_type == "WA" and (optidos := await self.get_optidos()):
            config_tree[OPTIDOS_CATEGORY] = AggCategory(
                key=OPTIDOS_CATEGORY, description="OptiDos", commands=optidos
            )
        return config_tree

    async def get_optidos(self) -> dict[str, Command]:
        """The OptiDos detergent trays of a washing machine, as config commands.

        They aren't in the category tree, but are read with 'getCommand' (or
        'getUserSettings' from hh 1.12) and written with 'set<command>' like the
        rest, so the usual select and number entities handle them.
        """
        commands: dict[str, Command] = {}
        for tray in ("A", "B"):
            detergent = f"detergent{tray}neutral"
            dosage = f"dosage{tray}"
            if self.hh_supports((1, 12, 0)):
                det = await self._user_setting(f"DETERGENT_{tray}")
                dos = await self._user_setting(f"DOSAGE_{tray}")
                det_value = OPTIDOS_DETERGENTS.get(str(det.get("set")))
                dos_value, low, high = dos.get("set"), dos.get("min"), dos.get("max")
            else:
                det = await self._optional_command(detergent)
                dos = await self._optional_command(dosage)
                det_value = det.get("value")
                dos_value = dos.get("value")
                low, high = sorted(dos.get("minMax") or [0, 0], key=float)[:2]
            if det_value is not None:
                commands[detergent] = Command(
                    type="selection",
                    description=f"Detergent {tray}",
                    command=detergent,
                    value=det_value,
                    alterable=True,
                    options=list(OPTIDOS_DETERGENTS.values()),
                )
            if dos_value is not None:
                commands[dosage] = Command(
                    type="range",
                    description=f"Dosage {tray}",
                    command=dosage,
                    value=str(dos_value),
                    alterable=True,
                    minMax=(str(low), str(high)),
                )
        return commands

    async def _optional_command(self, name: str) -> dict[str, Any]:
        return await self._command(
            "hh",
            command="getCommand",
            params={"value": name},
            expected_type=dict,
            attempts=2,
            value_on_err=dict,
        )

    async def _user_setting(self, setting_id: str) -> dict[str, Any]:
        data = await self._command(
            "hh",
            command="getUserSettings",
            params={"value": _compact_json({"id": setting_id})},
            expected_type=dict,
            attempts=2,
            value_on_err=dict,
        )
        value = data.get("value")
        return value if isinstance(value, dict) else {}

    async def get_installed_features(self) -> list[str]:
        """Paid V-ZUG Upgrades installed on the appliance (hh 1.7)."""
        return await self._command(
            "hh", command="getInstalledFeatures", expected_type=list, attempts=2
        )

    async def get_api_version(self, component: str) -> tuple[int, ...] | None:
        """'getAPIVersion' of the 'ai' or 'hh' API, ex. {"value":"1.12.0"}.

        Not every appliance knows it (the V-ZUG app then assumes 1.0.0), so None
        when it fails.
        """
        data = await self._command(
            component,
            command="getAPIVersion",
            expected_type=dict,
            attempts=1,
            value_on_err=lambda: {},
        )
        return parse_version(data.get("value"))

    async def get_mac_address(
        self, *, default_on_error: bool = False, attempts: int = 5
    ) -> str:
        return await self._command(
            "ai",
            command="getMacAddress",
            raw=True,
            attempts=attempts,
            value_on_err=(lambda: "") if default_on_error else None,
        )

    async def get_model_description(
        self, *, default_on_error: bool = False, attempts: int = 5
    ) -> str:
        return await self._command(
            "ai",
            command="getModelDescription",
            raw=True,
            attempts=attempts,
            value_on_err=(lambda: "") if default_on_error else None,
        )

    async def get_device_status(
        self, *, default_on_error: bool = False, attempts: int = 5
    ) -> DeviceStatus:
        return await self._command(
            "ai",
            command="getDeviceStatus",
            expected_type=dict,
            attempts=attempts,
            value_on_err=(lambda: DeviceStatus()) if default_on_error else None,
        )

    async def get_errors(self) -> list[str]:
        """Error codes shown on the display, '/hh getDeviceStatus' (hh 1.5).

        ex. {"displayedErrors":[...]}, older firmware calls the list 'errors'.
        Optional: an appliance that doesn't know the command has no errors.
        """
        data = await self._command(
            "hh",
            command="getDeviceStatus",
            expected_type=dict,
            attempts=2,
            value_on_err=dict,
        )
        errors = data.get("displayedErrors") or data.get("errors") or []
        return [str(error) for error in errors] if isinstance(errors, list) else []

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
            # ex. CombairSteamer V6000 60 answers 404 since a firmware update
            value_on_client_err=list,
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

    async def get_ai_fw_version(
        self, *, default_on_error: bool = False, attempts: int = 5
    ) -> AiFwVersion:
        return await self._command(
            "ai",
            command="getFWVersion",
            expected_type=dict,
            attempts=attempts,
            value_on_err=(lambda: AiFwVersion()) if default_on_error else None,
        )

    async def get_zh_mode(
        self, *, default_on_error: bool = False, attempts: int = 5
    ) -> int:
        data = await self._command(
            "hh",
            command="getZHMode",
            expected_type=dict,
            attempts=attempts,
            value_on_err=(lambda: {"value": -1}) if default_on_error else None,
        )
        return data.get("value", -1)

    async def get_eco_info(self, *, default_on_error: bool = False) -> EcoInfo:
        result = await self._command(
            "hh",
            command="getEcoInfo",
            expected_type=dict,
            value_on_err=(lambda: EcoInfo()) if default_on_error else None,
        )

        water_total = result.get("water", {}).get("total", 0)
        energy_total = result.get("energy", {}).get("total", 0)

        # If both water and energy totals are 0, we return an empty EcoInfo
        # This is to handle cases where the API returns 0s for both metrics.
        # Refrigerators have neither, only door openings.
        if water_total == 0 and energy_total == 0 and not result.get("doorOpenings"):
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

    async def get_program(self) -> list[Program]:
        # TODO: this is interesting but what can we do with it??
        # [{"id":52,"name":"Alltag Kurz","status":"selected","starttime":{"min":0,"max":86400,"step":600},"duration":{"set":2460}, "energySaving":{"set":false,"options":[true,false]},"optiStart":{"set":false},"steamfinish":{"set":false,"options":[true,false]},"partialload":{"set":false,"options":[true,false]},"rinsePlus":{"set":false,"options":[true,false]},"dryPlus":{"set":false,"options":[true,false]},"stepIds":[82,81,82,79,78,76,73,74,75,72,71,70]}]
        # [{"id":50,"name":"Eco",        "status":"selected","starttime":{"min":0,"max":86400,"step":600},"duration":{"set":22440},"energySaving":{"set":false,"options":[true,false]},"optiStart":{"set":false},"steamfinish":{"set":true, "options":[true,false]},"partialload":{"set":false,"options":[true,false]},"rinsePlus":{"set":false,"options":[true,false]},"dryPlus":{"set":false,"options":[true,false]},"stepIds":[79,81,79,78,74,75,72,70]}]
        raw_programs: list[dict[str, Any]] = await self._command(
            "hh",
            command="getProgram",
            expected_type=list,
        )
        return [Program.build(raw) for raw in raw_programs]

    async def set_program(
        self, program_id: int, options: dict[str, Any] | None = None
    ) -> list[Any]:
        # example options: {"id":50,"dryPlus":false,"energySaving":false,"partialload":false,"rinsePlus":false,"steamfinish":true}
        # also seen with just the "id" key
        if not options:
            options = {}
        options["id"] = program_id
        return await self.set_program_dto(options)

    async def set_program_dto(self, dto: dict[str, Any]) -> Any:
        """'setProgram' with typed values, ex. {"zone":"cookingChamber1","light":true}.

        hh 1.5 and newer take the whole object at once. Older appliances take one
        value per request and only these keys, in this order, like the V-ZUG app.
        """
        if self.hh_supports((1, 5, 0)):
            dtos = [dto]
        else:
            dtos = [{key: dto[key]} for key in _LEGACY_PROGRAM_KEYS if dto.get(key)]
        result = None
        for value in dtos:
            result = await self._command(
                "hh",
                command="setProgram",
                params={"value": _compact_json(value)},
                raw=True,
                attempts=2,
            )
        return result

    async def stop_program(self, zone: str | None = None) -> None:
        """End the running (or waiting) program, like Stop in the V-ZUG app.

        Recorded from the app: setProgram {"status":"idle"}. The appliance goes to
        standby and skips what is left, the final drying with the door opening too.
        Ovens stop one zone at a time. Before hh 1.3 the app sends 'doTurnOff'.
        """
        if not self.hh_supports((1, 3, 0)):
            await self._command("hh", command="doTurnOff", raw=True, attempts=2)
            return
        dto = {"status": "idle"}
        if zone:
            dto["zone"] = zone
        await self.set_program_dto(dto)

    async def get_all_program_ids(self) -> list[int]:
        # TODO: this gives us a nice list of ids that could be used with set_program, but we need a program id to name mapping
        return await self._command(
            "hh",
            command="getAllProgramIds",
            expected_type=list,
        )

    async def get_raw_programs(self, *, attempts: int = 5) -> list[dict[str, Any]]:
        """'getProgram' as the appliance sends it.

        Refrigerators answer with one entry per zone, ex.
        {"id":2000,"status":"active","temp":{"set":6.0,"act":6.0,"min":3.0,"max":8.0},
         "superCool":{"min":0,"max":86400},"partyCooling":{"min":0,"max":172800},
         "doorClosed":true,"zone":"fridge1"}
        A running timed function gains 'set' (requested seconds) and 'act' (seconds left).
        """
        return await self._command(
            "hh",
            command="getProgram",
            expected_type=list,
            attempts=attempts,
        )

    async def get_program_details(self, program_id: int) -> dict[str, Any]:
        """'getProgram' for one program id, without selecting it.

        This is how the V-ZUG app learns the program names, ex.
        {"id":51,"name":"Automatic","status":"idle","starttime":{...},...}
        """
        raw: list[dict[str, Any]] = await self._command(
            "hh",
            command="getProgram",
            params={"value": _compact_json({"id": program_id})},
            expected_type=list,
            attempts=2,
        )
        return raw[0] if raw else {}

    async def set_zone_value(self, zone: str, key: str, value: str) -> None:
        """Change one value of a zone, the way the V-ZUG app does it.

        The appliance addresses zones by name, not by program id, and wants every
        value as a string: {"zone":"fridge1","temp":"7"} or
        {"zone":"freezer1","superFreeze":"3600"} (seconds, "0" switches it off).
        Anything else is refused with error 400.03 / 400.04.
        """
        await self._command(
            "hh",
            command="setProgram",
            params={"value": _compact_json({"zone": zone, key: value})},
            raw=True,
            attempts=2,
        )

    async def get_cmd_value(self, name: str, *, attempts: int = 2) -> str:
        """Read a 'cmd' setting outside the category tree, ex. 'HolidayMode'."""
        content: str = await self._command(
            "hh",
            command=f"getcmd{name}",
            raw=True,
            attempts=attempts,
        )
        return content.strip()

    async def set_cmd_value(self, name: str, value: str) -> None:
        await self.set_command(f"cmd{name}", value)


class AuthenticationFailed(Exception): ...


OPTIDOS_CATEGORY = "optidos"
# 'getUserSettings' detergent ids -> the text 'setdetergent<tray>neutral' takes
OPTIDOS_DETERGENTS = {
    "BABY": "Baby detergent",
    "UNIVERSAL": "Universal detergent",
    "MILD": "Delicates detergent",
    "SOFTENER": "Fabric conditioner",
    "COLOR": "Colour detergent",
    "WOOL": "Woollens detergent",
    "BLACK": "Detergent for blacks",
    "WHITE": "Detergent for whites",
    "OUTDOOR": "Outdoor garm. deterg",
    "NO_DETERGENT": "No detergent",
}

# the only 'setProgram' keys appliances before hh 1.5 accept, one per request
_LEGACY_PROGRAM_KEYS = (
    "id",
    "duration",
    "temp",
    "templevel",
    "probetemp",
    "mw",
    "mwlevel",
)


def parse_version(raw: Any) -> tuple[int, ...] | None:
    """'1.12.0' -> (1, 12, 0), None if it isn't a version."""
    try:
        version = tuple(int(part) for part in str(raw).strip().split("."))
    except ValueError:
        return None
    return version if len(version) >= 2 else None


def _compact_json(value: Any) -> str:
    """JSON without spaces.

    The appliance answers 'setProgram' with '{"id": 50}' with 400 Bad Request and
    only accepts '{"id":50}', which is what the V-ZUG app sends.
    """
    return json.dumps(value, separators=(",", ":"))
