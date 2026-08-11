import contextlib
import logging
from datetime import timedelta

import yarl
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import api
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

StateCoordinator = DataUpdateCoordinator[api.AggState]
UpdateCoordinator = DataUpdateCoordinator[api.AggUpdateStatus]
UPDATE_COORD_IDLE_INTERVAL = timedelta(hours=6)
UPDATE_COORD_ACTIVE_INTERVAL = timedelta(seconds=5)

ConfigCoordinator = DataUpdateCoordinator[api.AggConfig]
# the config tree is a snapshot of the appliance's settings, so it barely ever
# changes on its own. Polling it every few minutes only widens the window for the
# transient failures this API is prone to, so it is refreshed on demand instead:
# whenever the appliance starts or finishes a program, and after every write.
CONFIG_COORD_INTERVAL = timedelta(hours=1)

# how many consecutive bad updates we cover by keeping the previous data around.
# the appliance answers '200 []' or fails outright when it's busy and that must not
# reach the entities, but the grace period has to be bounded so a genuine change
# (ex. the eco counters being reset) still gets through.
CONFIG_MAX_STALE_UPDATES = 3
STATE_MAX_STALE_UPDATES = 3


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
        base_url: yarl.URL,
        credentials: api.Credentials | None,
    ) -> None:
        self.hass = hass
        self.client = api.VZugApi(
            base_url,
            credentials=credentials,
        )

        self.state_coord = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name="state",
            update_interval=timedelta(seconds=30),
            update_method=self._fetch_state,
        )
        self.update_coord = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name="update",
            update_interval=UPDATE_COORD_IDLE_INTERVAL,
            update_method=self._fetch_update,
        )
        self.config_coord = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name="config",
            update_interval=CONFIG_COORD_INTERVAL,
            update_method=self._fetch_config,
        )

        # the rest will be set on first refresh
        self.unique_id_prefix = ""
        self.device_info = DeviceInfo()
        self._first_refresh_done = False
        self._config_stale_count = 0
        self._eco_stale_count = 0
        self._device_active: bool | None = None

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

        self._first_refresh_done = True

    async def _fetch_state(self) -> api.AggState:
        async with detect_auth_failed():
            state = await self.client.aggregate_state(
                default_on_error=self._first_refresh_done
            )

        # an all-zero 'getEcoInfo' response is mapped to an empty EcoInfo, which would
        # put every eco sensor to 'unknown'. Keep the previous values for a while
        # instead - but not forever, the counters can legitimately be reset to 0.
        previous = self.state_coord.data
        if not state.eco_info and previous is not None and previous.eco_info:
            if self._eco_stale_count < STATE_MAX_STALE_UPDATES:
                self._eco_stale_count += 1
                _LOGGER.debug(
                    "eco info is empty (%s/%s), keeping previous values",
                    self._eco_stale_count,
                    STATE_MAX_STALE_UPDATES,
                )
                state.eco_info = previous.eco_info
        else:
            self._eco_stale_count = 0

        self._track_activity(state.device)
        return state

    def _track_activity(self, device: api.DeviceStatus) -> None:
        """Refresh the config tree whenever the appliance starts or finishes."""
        inactive = device.get("Inactive")
        if inactive not in ("true", "false"):
            # unknown state, don't guess
            return

        active = inactive == "false"
        if self._device_active is not None and active != self._device_active:
            # the eco statistics in the config tree ('ecomXstatXtotal' and friends)
            # are updated when a program completes, and someone standing at the
            # appliance may have changed settings on its panel
            _LOGGER.debug("device activity changed to %s, refreshing config", active)
            self.hass.async_create_task(self.config_coord.async_request_refresh())
        self._device_active = active

    async def _fetch_update(self) -> api.AggUpdateStatus:
        async with detect_auth_failed():
            data = await self.client.aggregate_update_status(
                supports_update_status=self.meta.supports_update_status(),
                default_on_error=True,  # we allow the update to fail because it's not essential
            )
        if data.update.get("status") in ("idle", None):
            self.update_coord.update_interval = UPDATE_COORD_IDLE_INTERVAL
        else:
            self.update_coord.update_interval = UPDATE_COORD_ACTIVE_INTERVAL
        return data

    async def _fetch_config(self) -> api.AggConfig:
        previous = self.config_coord.data
        try:
            async with detect_auth_failed():
                config_tree = await self.client.aggregate_config()
            if not config_tree and previous:
                # the appliance answers '200 []' to 'getCategories' when it's busy.
                # An empty result is only believable if the previous one was empty too.
                raise UpdateFailed("getCategories returned empty")
        except ConfigEntryAuthFailed:
            raise
        except Exception as exc:
            # 'previous is None' means we never had a successful update, so there is
            # nothing to keep and the caller should see the failure
            if previous is None or self._config_stale_count >= CONFIG_MAX_STALE_UPDATES:
                raise
            self._config_stale_count += 1
            _LOGGER.debug(
                "config update failed (%s/%s), keeping previous data: %r",
                self._config_stale_count,
                CONFIG_MAX_STALE_UPDATES,
                exc,
            )
            return previous

        self._config_stale_count = 0
        return config_tree


@contextlib.asynccontextmanager
async def detect_auth_failed():
    try:
        yield
    except api.AuthenticationFailed:
        raise ConfigEntryAuthFailed
