from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import zones
from .entity import user_config_entities, UserConfigEntity, vzug_action, ZoneEntity
from .helpers import snake
from .coordinator import Shared, VZugConfigEntry

# the appliance handles one request at a time, so do the actions
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VZugConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared = config_entry.runtime_data

    entities: list[SwitchEntity] = []

    entities.extend(
        user_config_entities(
            shared,
            async_add_entities,
            lambda c: c.get("type") == "boolean" and c.get("alterable", True),
            UserConfig,
        )
    )

    entities.extend(_zone_entities(shared))
    async_add_entities(entities)


def _zone_entities(shared: Shared) -> list[SwitchEntity]:
    if shared.zone_coord is None:
        return []
    data = shared.zone_coord.data
    entities: list[SwitchEntity] = []
    for key in zones.BOOST_KEYS:
        entities.extend(
            TimedFunction(shared, zone=zone, key=key)
            for zone in zones.zones_with(data.zones, key)
        )
    if party_zones := zones.zones_with(data.zones, zones.PARTY_KEY):
        entities.append(TimedFunction(shared, zone=party_zones[0], key=zones.PARTY_KEY))
    entities.extend(
        Mode(shared, mode=mode) for mode in zones.SWITCH_MODES if mode in data.modes
    )
    entities.extend(
        Light(shared, zone=zone)
        for zone, zone_data in data.zones.items()
        if zones.can_toggle(zone_data, "light")
    )
    return entities


class Light(ZoneEntity, SwitchEntity):
    """The oven light, 'light' in 'setProgram' with real booleans."""

    _attr_translation_key = "oven_light"

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key="light")

    @property
    def is_on(self) -> bool | None:
        return zones.flag(self.zone_data, self.vzug_key)

    @vzug_action
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    @vzug_action
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, on: bool) -> None:
        await self.shared.client.set_program_dto({"zone": self.vzug_zone, "light": on})
        await self.coordinator.async_request_refresh()


class TimedFunction(ZoneEntity, SwitchEntity):
    """SuperCool, SuperFreeze or PartyCooling.

    On runs it for the duration set on the matching number entity, the appliance
    switches it off by itself when that is over.
    """

    def __init__(self, shared: Shared, *, zone: str, key: str) -> None:
        super().__init__(shared, zone=zone, key=key)
        self._attr_translation_key = snake(key)

    @property
    def is_on(self) -> bool:
        return zones.is_running(self.zone_data, self.vzug_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "remaining_seconds": zones.remaining_seconds(self.zone_data, self.vzug_key)
        }

    @vzug_action
    async def async_turn_on(self, **kwargs: Any) -> None:
        hours = self.shared.boost_hours.get(self.vzug_key, 12.0)
        await self._write_zone(zones.format_value(int(hours * 3600)))

    @vzug_action
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write_zone("0")


class Mode(ZoneEntity, SwitchEntity):
    """An on/off 'cmd' setting of the whole appliance (Holiday, SilentPlus)."""

    def __init__(self, shared: Shared, *, mode: str) -> None:
        super().__init__(shared, zone="", key=mode)
        self._attr_translation_key = snake(mode)

    @property
    def is_on(self) -> bool | None:
        return zones.mode_is_on(self.coordinator.data.modes.get(self.vzug_key))

    @vzug_action
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    @vzug_action
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, on: bool) -> None:
        await self.shared.client.set_cmd_value(self.vzug_key, "true" if on else "false")
        await self.coordinator.async_request_refresh()


class UserConfig(SwitchEntity, UserConfigEntity):
    @property
    def is_on(self) -> bool | None:
        value = self.vzug_command.get("value")
        match value:
            case "true":
                return True
            case "false":
                return False
            case _:
                return None

    @vzug_action
    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._vzug_set_state(True)

    @vzug_action
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._vzug_set_state(False)

    async def _vzug_set_state(self, on: bool) -> None:
        await self.shared.client.set_command(
            self.vzug_command_key, "true" if on else "false"
        )
        await self.coordinator.async_request_refresh()
