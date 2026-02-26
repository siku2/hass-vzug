import contextlib
import logging
from datetime import timedelta

import yarl
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import api
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_COORD_IDLE_INTERVAL = timedelta(hours=6)
UPDATE_COORD_ACTIVE_INTERVAL = timedelta(seconds=5)


class StateCoordinator(DataUpdateCoordinator[api.AggState]):
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: api.VZugApi,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="state",
            update_interval=timedelta(seconds=30),
        )
        self._client = client
        self._first_refresh_done = False

    async def _async_update_data(self) -> api.AggState:
        async with detect_auth_failed():
            data = await self._client.aggregate_state(
                default_on_error=self._first_refresh_done
            )
        self._first_refresh_done = True
        return data


class UpdateCoordinator(DataUpdateCoordinator[api.AggUpdateStatus]):
    meta: api.AggMeta

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: api.VZugApi,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="update",
            update_interval=UPDATE_COORD_IDLE_INTERVAL,
        )
        self._client = client

    async def _async_update_data(self) -> api.AggUpdateStatus:
        async with detect_auth_failed():
            data = await self._client.aggregate_update_status(
                supports_update_status=self.meta.supports_update_status(),
                default_on_error=True,  # we allow the update to fail because it's not essential
            )
        if data.update.get("status") in ("idle", None):
            self.update_interval = UPDATE_COORD_IDLE_INTERVAL
        else:
            self.update_interval = UPDATE_COORD_ACTIVE_INTERVAL
        return data


class ConfigCoordinator(DataUpdateCoordinator[api.AggConfig]):
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: api.VZugApi,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="config",
            update_interval=timedelta(minutes=5),
        )
        self._client = client

    async def _async_update_data(self) -> api.AggConfig:
        async with detect_auth_failed():
            return await self._client.aggregate_config()


class Shared:
    hass: HomeAssistant
    client: api.VZugApi

    state_coord: StateCoordinator
    update_coord: UpdateCoordinator
    config_coord: ConfigCoordinator

    unique_id_prefix: str
    meta: api.AggMeta
    device_info: DeviceInfo

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        base_url: yarl.URL,
        credentials: api.Credentials | None,
    ) -> None:
        self.hass = hass
        self.client = api.VZugApi(
            base_url,
            credentials=credentials,
        )

        self.state_coord = StateCoordinator(hass, config_entry, self.client)
        self.update_coord = UpdateCoordinator(hass, config_entry, self.client)
        self.config_coord = ConfigCoordinator(hass, config_entry, self.client)

        # the rest will be set on first refresh
        self.unique_id_prefix = ""
        self.device_info = DeviceInfo()

    async def async_config_entry_first_refresh(self) -> None:
        async with detect_auth_failed():
            self.meta = await self.client.aggregate_meta()

        self.update_coord.meta = self.meta

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

    async def _post_first_refresh(self) -> None:
        mac_addr = dr.format_mac(self.meta.mac_address)
        self.unique_id_prefix = mac_addr
        if not self.unique_id_prefix:
            _LOGGER.warn(
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


@contextlib.asynccontextmanager
async def detect_auth_failed():
    try:
        yield
    except api.AuthenticationFailed:
        raise ConfigEntryAuthFailed
