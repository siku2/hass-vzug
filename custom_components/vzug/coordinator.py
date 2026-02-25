from __future__ import annotations

import contextlib
import logging
from datetime import timedelta

import httpx
import yarl
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.httpx_client import create_async_httpx_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import api
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_COORD_IDLE_INTERVAL = timedelta(hours=6)
UPDATE_COORD_ACTIVE_INTERVAL = timedelta(seconds=5)


class StateCoordinator(DataUpdateCoordinator[api.AggState]):
    def __init__(self, shared: Shared, config_entry: ConfigEntry) -> None:
        super().__init__(
            shared.hass,
            _LOGGER,
            name="state",
            update_interval=timedelta(seconds=30),
            config_entry=config_entry,
            always_update=False,
        )
        self.shared = shared

    async def _async_update_data(self) -> api.AggState:
        async with detect_auth_failed():
            return await self.shared.client.aggregate_state(
                default_on_error=self.shared._first_refresh_done
            )


class UpdateCoordinator(DataUpdateCoordinator[api.AggUpdateStatus]):
    def __init__(self, shared: Shared, config_entry: ConfigEntry) -> None:
        super().__init__(
            shared.hass,
            _LOGGER,
            name="update",
            update_interval=UPDATE_COORD_IDLE_INTERVAL,
            config_entry=config_entry,
            always_update=False,
        )
        self.shared = shared

    async def _async_update_data(self) -> api.AggUpdateStatus:
        async with detect_auth_failed():
            data = await self.shared.client.aggregate_update_status(
                supports_update_status=self.shared.meta.supports_update_status(),
                default_on_error=True,  # we allow the update to fail because it's not essential
            )
        if data.update.get("status") in ("idle", None):
            self.update_interval = UPDATE_COORD_IDLE_INTERVAL
        else:
            self.update_interval = UPDATE_COORD_ACTIVE_INTERVAL
        return data


class ProgramCoordinator(DataUpdateCoordinator[api.AggProgramState]):
    def __init__(self, shared: Shared, config_entry: ConfigEntry) -> None:
        super().__init__(
            shared.hass,
            _LOGGER,
            name="program",
            update_interval=timedelta(seconds=30),
            config_entry=config_entry,
            always_update=False,
        )
        self.shared = shared

    async def _async_update_data(self) -> api.AggProgramState:
        async with detect_auth_failed():
            return await self.shared.client.aggregate_program(
                default_on_error=True,
            )


class ConfigCoordinator(DataUpdateCoordinator[api.AggConfig]):
    def __init__(self, shared: Shared, config_entry: ConfigEntry) -> None:
        super().__init__(
            shared.hass,
            _LOGGER,
            name="config",
            update_interval=timedelta(minutes=5),
            config_entry=config_entry,
            always_update=False,
        )
        self.shared = shared

    async def _async_update_data(self) -> api.AggConfig:
        async with detect_auth_failed():
            return await self.shared.client.aggregate_config()


class Shared:
    hass: HomeAssistant
    client: api.VZugApi

    state_coord: StateCoordinator
    update_coord: UpdateCoordinator
    config_coord: ConfigCoordinator
    program_coord: ProgramCoordinator | None

    unique_id_prefix: str
    meta: api.AggMeta
    device_info: DeviceInfo

    program_list: dict[int, str]
    cloud_status: api.CloudStatus

    def __init__(
        self,
        hass: HomeAssistant,
        base_url: yarl.URL,
        credentials: api.Credentials | None,
        *,
        config_entry: ConfigEntry,
    ) -> None:
        self.hass = hass
        auth = (
            httpx.DigestAuth(
                username=credentials.username, password=credentials.password
            )
            if credentials
            else None
        )
        transport = httpx.AsyncHTTPTransport(
            verify=False,
            limits=httpx.Limits(max_connections=3, max_keepalive_connections=1),
            retries=5,
        )
        httpx_client = create_async_httpx_client(
            hass, verify_ssl=False, auth=auth, transport=transport
        )
        self.client = api.VZugApi(base_url, client=httpx_client)

        # the rest will be set on first refresh
        self.unique_id_prefix = ""
        self.device_info = DeviceInfo()
        self._first_refresh_done = False
        self.program_coord = None
        self._config_entry = config_entry

        self.state_coord = StateCoordinator(self, config_entry)
        self.update_coord = UpdateCoordinator(self, config_entry)
        self.config_coord = ConfigCoordinator(self, config_entry)

    async def async_config_entry_first_refresh(self) -> None:
        async with detect_auth_failed():
            self.meta = await self.client.aggregate_meta()

        await self.state_coord.async_config_entry_first_refresh()
        await self.update_coord.async_config_entry_first_refresh()
        await self.config_coord.async_config_entry_first_refresh()

        try:
            await self._post_first_refresh()
        except Exception as exc:
            _LOGGER.exception("init failed")
            raise ConfigEntryNotReady() from exc

    async def async_shutdown(self) -> None:
        await self.state_coord.async_shutdown()
        await self.update_coord.async_shutdown()
        await self.config_coord.async_shutdown()
        if self.program_coord is not None:
            await self.program_coord.async_shutdown()

    async def _post_first_refresh(self) -> None:
        mac_addr = dr.format_mac(self.meta.mac_address)
        self.unique_id_prefix = mac_addr
        if not self.unique_id_prefix:
            _LOGGER.warning(
                "unable to determine unique id from device data: %s", self.meta
            )

        self.device_info.update(
            DeviceInfo(
                configuration_url=str(self.client.base_url),
                identifiers={(DOMAIN, self.meta.serial_number)},
                name=self.meta.create_name(),
                hw_version=self.update_coord.data.ai_fw_version.get("HW"),
                sw_version=self.update_coord.data.ai_fw_version.get("SW"),
                connections={(dr.CONNECTION_NETWORK_MAC, mac_addr)},
                model=self.meta.model_name,
            )
        )

        # Conditionally start ProgramCoordinator for devices with zone data
        try:
            program_state = await self.client.aggregate_program()
            has_zone_data = any(
                "temp" in zone
                or "doorClosed" in zone
                or "light" in zone
                or "preheatStatus" in zone
                or "probeInserted" in zone
                for zone in program_state.zones
            )
        except Exception:
            _LOGGER.debug("device does not support program zones", exc_info=True)
            has_zone_data = False

        if has_zone_data:
            self.program_coord = ProgramCoordinator(self, self._config_entry)
            await self.program_coord.async_config_entry_first_refresh()

        # Fetch program list (static, fetched once)
        try:
            self.program_list = await self.client.get_program_list()
        except Exception:
            _LOGGER.debug("failed to fetch program list", exc_info=True)
            self.program_list = {}

        # Fetch cloud status (static, fetched once)
        try:
            self.cloud_status = await self.client.get_cloud_status(
                default_on_error=True
            )
        except Exception:
            _LOGGER.debug("failed to fetch cloud status", exc_info=True)
            self.cloud_status = api.CloudStatus()

        self._first_refresh_done = True


@contextlib.asynccontextmanager
async def detect_auth_failed():
    try:
        yield
    except api.AuthenticationFailed:
        raise ConfigEntryAuthFailed
