import contextlib
import logging
from datetime import UTC, datetime, timedelta

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
# 'getDeviceStatus' wakes the appliance and it stays awake for ~20s afterwards, so
# polling it every 30s keeps the appliance awake around the clock. While a program
# runs it is awake anyway and polling is free; in standby we only ask the AI module
# for notifications, which doesn't disturb the appliance at all, and pay for a real
# status probe every few minutes to catch a program someone started by hand.
STATE_COORD_ACTIVE_INTERVAL = timedelta(seconds=30)
STATE_COORD_IDLE_INTERVAL = timedelta(seconds=60)
STATE_COORD_IDLE_PROBE_INTERVAL = timedelta(minutes=5)

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
            update_interval=STATE_COORD_ACTIVE_INTERVAL,
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
        self._last_device_probe: datetime | None = None
        self._last_notification: str | None = None

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
        previous = self.state_coord.data
        probe = self._device_probe_due()

        async with detect_auth_failed():
            state = await self.client.aggregate_state(
                default_on_error=self._first_refresh_done,
                include_device=probe,
                include_eco=probe,
            )

            if self._note_notifications(state.notifications) and not probe:
                # something happened at the appliance: a program finished, or a
                # timed one started. It is awake now anyway, so this costs nothing.
                _LOGGER.debug("new notification, fetching the full state")
                probe = True
                state = await self.client.aggregate_state(
                    default_on_error=self._first_refresh_done
                )
                self.hass.async_create_task(self.config_coord.async_request_refresh())

        if not probe:
            return self._carry_over(state, previous)

        self._last_device_probe = datetime.now(UTC)

        # an all-zero 'getEcoInfo' response is mapped to an empty EcoInfo, which would
        # put every eco sensor to 'unknown'. Keep the previous values for a while
        # instead - but not forever, the counters can legitimately be reset to 0.
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
        self.state_coord.update_interval = (
            STATE_COORD_IDLE_INTERVAL
            if self._device_active is False
            else STATE_COORD_ACTIVE_INTERVAL
        )
        return state

    async def async_probe_device(self) -> None:
        """Bring everything up to date, waking the appliance if necessary.

        In standby the state updates deliberately leave the appliance alone and the
        config tree is only refreshed hourly, so neither a plain refresh nor waiting
        gets fresh data. This is the way to ask for it anyway. Both coordinators are
        included because the appliance is being woken either way, and a settings
        change made on its panel is exactly the kind of thing someone would press
        this for.
        """
        self._last_device_probe = None
        await self.state_coord.async_request_refresh()
        await self.config_coord.async_request_refresh()

    def _device_probe_due(self) -> bool:
        """Whether this poll may wake the appliance up."""
        if self._device_active is not False:
            # running, or we don't know yet - either way it isn't asleep
            return True
        if self._last_device_probe is None:
            return True
        age = datetime.now(UTC) - self._last_device_probe
        return age >= STATE_COORD_IDLE_PROBE_INTERVAL

    def _note_notifications(self, notifications: list[api.PushNotification]) -> bool:
        """Remember the most recent notification, reporting whether it is new."""
        try:
            latest = notifications[0]["date"]
        except LookupError:
            return False

        previous, self._last_notification = self._last_notification, latest
        return previous is not None and previous != latest

    def _carry_over(
        self, state: api.AggState, previous: api.AggState | None
    ) -> api.AggState:
        """Fill in the values we deliberately didn't ask for."""
        if previous is None:
            return state

        # 'device_fetched_at' has to travel with the device data: ProgramEnd computes
        # the finishing time as 'device_fetched_at + remaining', so a fresh timestamp
        # on stale data would push the countdown further out on every poll
        state.device = previous.device
        state.device_fetched_at = previous.device_fetched_at
        state.eco_info = previous.eco_info
        state.zh_mode = previous.zh_mode
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
