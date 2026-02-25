from __future__ import annotations

import asyncio
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
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import api
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 10

STATE_COORD_IDLE_INTERVAL = timedelta(seconds=60)
STATE_COORD_ACTIVE_INTERVAL = timedelta(seconds=10)

UPDATE_COORD_IDLE_INTERVAL = timedelta(hours=1)
UPDATE_COORD_ACTIVE_INTERVAL = timedelta(seconds=5)

PROGRAM_COORD_IDLE_INTERVAL = timedelta(seconds=60)
PROGRAM_COORD_ACTIVE_INTERVAL = timedelta(seconds=10)


class StateCoordinator(DataUpdateCoordinator[api.AggState]):
    def __init__(self, shared: Shared, config_entry: ConfigEntry) -> None:
        super().__init__(
            shared.hass,
            _LOGGER,
            name="state",
            update_interval=STATE_COORD_IDLE_INTERVAL,
            config_entry=config_entry,
            always_update=False,
        )
        self.shared = shared

    async def _async_update_data(self) -> api.AggState:
        async with detect_auth_failed():
            data = await self.shared.client.aggregate_state(
                default_on_error=self.shared._first_refresh_done
            )
        if data.device.get("Inactive") == "true":
            self.update_interval = STATE_COORD_IDLE_INTERVAL
        else:
            self.update_interval = STATE_COORD_ACTIVE_INTERVAL
        return data


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
    def __init__(
        self,
        shared: Shared,
        config_entry: ConfigEntry,
        *,
        initial_data: api.AggProgramState | None = None,
    ) -> None:
        super().__init__(
            shared.hass,
            _LOGGER,
            name="program",
            update_interval=PROGRAM_COORD_IDLE_INTERVAL,
            config_entry=config_entry,
            always_update=False,
        )
        self.shared = shared
        self._initial_data = initial_data

    async def _async_update_data(self) -> api.AggProgramState:
        if self._initial_data is not None:
            data = self._initial_data
            self._initial_data = None
            return data
        async with detect_auth_failed():
            data = await self.shared.client.aggregate_program(
                default_on_error=True,
            )
        has_active = any(z.get("status") == "active" for z in data.zones)
        if has_active:
            self.update_interval = PROGRAM_COORD_ACTIVE_INTERVAL
        else:
            self.update_interval = PROGRAM_COORD_IDLE_INTERVAL
        return data


class ConfigCoordinator(DataUpdateCoordinator[api.AggConfig]):
    def __init__(self, shared: Shared, config_entry: ConfigEntry) -> None:
        super().__init__(
            shared.hass,
            _LOGGER,
            name="config",
            update_interval=timedelta(minutes=30),
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
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            retries=3,
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

        store = Store(
            self.hass,
            STORAGE_VERSION,
            f"vzug_{self.meta.mac_address.replace(':', '').lower()}",
        )
        cached = await store.async_load()

        if cached:
            try:
                self.state_coord.async_set_updated_data(
                    api.AggState.from_cache(cached["state"])
                )
                self.update_coord.async_set_updated_data(
                    api.AggUpdateStatus.from_cache(cached["update"])
                )
                self.config_coord.async_set_updated_data(
                    api.agg_config_from_cache(cached["config"])
                )
                _LOGGER.debug("restored coordinator data from cache")
                # Schedule non-blocking background refresh
                for coord in (self.state_coord, self.update_coord, self.config_coord):
                    self.hass.async_create_task(coord.async_request_refresh())
            except Exception:
                _LOGGER.debug(
                    "failed to restore from cache, falling back to network",
                    exc_info=True,
                )
                cached = None

        if not cached:
            await asyncio.gather(
                self.state_coord.async_config_entry_first_refresh(),
                self.update_coord.async_config_entry_first_refresh(),
                self.config_coord.async_config_entry_first_refresh(),
            )
            _LOGGER.debug("coordinator first refresh (network) complete")

        try:
            await self._post_first_refresh()
        except Exception as exc:
            _LOGGER.exception("init failed")
            raise ConfigEntryNotReady() from exc

        self._store = store
        self._schedule_save()

        # Save on every successful coordinator update
        for coord in (self.state_coord, self.update_coord, self.config_coord):
            coord.async_add_listener(self._schedule_save)

    def _schedule_save(self) -> None:
        if (
            self.state_coord.data is not None
            and self.update_coord.data is not None
            and self.config_coord.data is not None
        ):
            self._store.async_delay_save(self._serialize_data, SAVE_DELAY)

    def _serialize_data(self) -> dict:
        return {
            "state": self.state_coord.data.to_cache(),
            "update": self.update_coord.data.to_cache(),
            "config": api.agg_config_to_cache(self.config_coord.data),
        }

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

        # Fetch program state, program list, and cloud status in parallel
        program_state, program_list, cloud_status = await asyncio.gather(
            self._fetch_program_state(),
            self._fetch_program_list(),
            self._fetch_cloud_status(),
        )

        # Conditionally start ProgramCoordinator for devices with zone data
        if program_state is not None:
            has_zone_data = any(
                "temp" in zone
                or "doorClosed" in zone
                or "light" in zone
                or "preheatStatus" in zone
                or "probeInserted" in zone
                for zone in program_state.zones
            )
            if has_zone_data:
                self.program_coord = ProgramCoordinator(
                    self, self._config_entry, initial_data=program_state
                )
                await self.program_coord.async_config_entry_first_refresh()

        self.program_list = program_list
        self.cloud_status = cloud_status
        self._first_refresh_done = True

    async def _fetch_program_state(self) -> api.AggProgramState | None:
        try:
            return await self.client.aggregate_program()
        except Exception:
            _LOGGER.debug("device does not support program zones", exc_info=True)
            return None

    async def _fetch_program_list(self) -> dict[int, str]:
        try:
            return await self.client.get_program_list()
        except Exception:
            _LOGGER.debug("failed to fetch program list", exc_info=True)
            return {}

    async def _fetch_cloud_status(self) -> api.CloudStatus:
        try:
            return await self.client.get_cloud_status(default_on_error=True)
        except Exception:
            _LOGGER.debug("failed to fetch cloud status", exc_info=True)
            return api.CloudStatus()


@contextlib.asynccontextmanager
async def detect_auth_failed():
    try:
        yield
    except api.AuthenticationFailed:
        raise ConfigEntryAuthFailed
