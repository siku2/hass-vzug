from typing import Any

import httpx
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import zones
from .const import DOMAIN
from .helpers import UserConfigEntity, ZoneEntity
from .shared import ProgramCoordinator, Shared


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared: Shared = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[ButtonEntity] = [RefreshNow(shared)]
    if shared.meta.supports_update_status():
        entities.append(CheckUpdate(shared))

    entities.extend(
        UserConfig(
            shared,
            category_key=category.key,
            command_key=command.get("command", ""),
        )
        for category in shared.config_coord.data.values()
        for command in category.commands.values()
        if command.get("type") == "action"
    )

    if shared.program_coord is not None:
        entities.append(SendProgram(shared))
        entities.append(StopProgram(shared))
        if shared.meta.machine_type != "GK":  # never switch on a hob remotely
            entities.append(StartProgram(shared))
    if shared.zone_coord is not None:
        for zone in shared.zone_coord.data.zones:
            if zones.is_program_zone(zone):
                entities.append(StopZone(shared, zone=zone))
            if zones.is_warming_drawer(zone) and shared.client.hh_supports((1, 5, 0)):
                entities.append(StartWarmingDrawer(shared, zone=zone))

    async_add_entities(entities)


class StopProgram(CoordinatorEntity[ProgramCoordinator], ButtonEntity):
    """'Stop' in the V-ZUG app: end the running or waiting program."""

    _attr_has_entity_name = True
    _attr_translation_key = "stop_program"
    _attr_icon = "mdi:stop"

    def __init__(self, shared: Shared) -> None:
        assert shared.program_coord is not None
        super().__init__(shared.program_coord)
        self.shared = shared
        self._attr_unique_id = f"{shared.unique_id_prefix}-stop-program"
        self._attr_device_info = shared.device_info

    async def async_press(self) -> None:
        await self.shared.client.stop_program()
        await self.coordinator.async_request_refresh()


class StopZone(ZoneEntity, ButtonEntity):
    """Stop the program of one zone (oven, warming drawer)."""

    _attr_icon = "mdi:stop"

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key="stop")
        if zones.is_warming_drawer(zone):
            self._attr_translation_key = "stop_warming_drawer"
        else:
            self._attr_translation_key = "stop_program"

    async def async_press(self) -> None:
        await self.shared.client.stop_program(self.vzug_zone)
        await self.coordinator.async_request_refresh()


class StartWarmingDrawer(ZoneEntity, ButtonEntity):
    """Select the warming drawer for the set duration, as the V-ZUG app does."""

    _attr_translation_key = "start_warming_drawer"
    _attr_icon = "mdi:play"

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key="start")

    async def async_press(self) -> None:
        minutes = self.shared.warming_drawer_minutes.get(self.vzug_zone, 120)
        await self.shared.client.set_program_dto(
            {
                "id": zones.WARMING_DRAWER_PROGRAM,
                "zone": self.vzug_zone,
                "duration": int(minutes * 60),
                "status": "selected",
            }
        )
        await self.coordinator.async_request_refresh()


class SendProgram(CoordinatorEntity[ProgramCoordinator], ButtonEntity):
    """'Send to appliance' in the V-ZUG app: transfer the selected program.

    The appliance starts it once its door is closed. There is no way to start a
    program remotely without that, the appliance insists on it.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "send_program"
    _attr_icon = "mdi:send"

    def __init__(self, shared: Shared) -> None:
        assert shared.program_coord is not None
        super().__init__(shared.program_coord)
        self.shared = shared
        self._attr_unique_id = f"{shared.unique_id_prefix}-send-program"
        self._attr_device_info = shared.device_info

    async def async_press(self) -> None:
        # the selection might have been changed on the panel since the last poll
        await self.coordinator.async_refresh()
        current = self.coordinator.data.current
        if current is None or not isinstance(current.get("id"), int):
            raise HomeAssistantError("Select a program first")
        options: dict[str, Any] = dict(zones.program_options(current))
        delay = zones.start_delay_seconds(current, self.shared.start_delay_hours)
        if delay:
            options[zones.START_DELAY_KEY] = delay
        if zone := getattr(self.shared, "program_zone", None):
            # like the V-ZUG app, an oven doesn't take a new program while one runs
            if current.get("status") in ("active", "timed"):
                raise HomeAssistantError("Stop the running program first")
            options["zone"] = zone
            options.update(
                zones.program_settings(current, self.shared.program_settings)
            )
        await self.shared.client.set_program(current["id"], options)
        # a delay applies to this one program, the next one starts right away again
        self.shared.start_delay_hours = 0.0
        await self.coordinator.async_request_refresh()


class StartProgram(CoordinatorEntity[ProgramCoordinator], ButtonEntity):
    """Experimental: start the selected program remotely.

    The V-ZUG app never does this, it leaves starting to someone at the
    appliance, and appliances may well refuse. Disabled by default: enable it
    only if you accept an oven or dishwasher starting without anyone there.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "start_program"
    _attr_icon = "mdi:play"
    _attr_entity_registry_enabled_default = False

    def __init__(self, shared: Shared) -> None:
        assert shared.program_coord is not None
        super().__init__(shared.program_coord)
        self.shared = shared
        self._attr_unique_id = f"{shared.unique_id_prefix}-start-program"
        self._attr_device_info = shared.device_info

    async def async_press(self) -> None:
        dto: dict[str, Any] = {"status": "active"}
        if zone := getattr(self.shared, "program_zone", None):
            dto["zone"] = zone
        try:
            await self.shared.client.set_program_dto(dto)
        except httpx.HTTPStatusError as err:
            raise HomeAssistantError(
                f"The appliance refused to start: {err.response.status_code} "
                f"{err.response.text.strip()}"
            ) from err
        await self.coordinator.async_request_refresh()


class RefreshNow(ButtonEntity):
    """Bring every value up to date right now, waking the appliance if necessary.

    While the appliance is in standby the state updates only talk to the AI module
    so it can stay asleep, and the config tree is only read hourly. Both are a
    deliberate trade-off, and this is the way out of it: for someone who just
    changed a setting on the appliance's panel, or for an automation that knows
    better than the integration does - a smart plug reporting power draw, a door
    contact, a motion sensor in the laundry room.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_translation_key = "refresh_now"

    def __init__(self, shared: Shared) -> None:
        self.shared = shared

        self._attr_unique_id = f"{shared.unique_id_prefix}-refresh-now"
        self._attr_device_info = shared.device_info

    async def async_press(self) -> None:
        await self.shared.async_probe_device()


class CheckUpdate(ButtonEntity):
    _attr_device_class = ButtonDeviceClass.UPDATE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_translation_key = "check_update"

    def __init__(self, shared: Shared) -> None:
        self.shared = shared

        self._attr_unique_id = f"{shared.unique_id_prefix}-check-update"
        self._attr_device_info = shared.device_info

    async def async_press(self) -> None:
        await self.shared.client.check_for_updates()
        await self.shared.update_coord.async_request_refresh()


class UserConfig(ButtonEntity, UserConfigEntity):
    async def async_press(self) -> None:
        await self.shared.client.do_command_action(self.vzug_command_key)
