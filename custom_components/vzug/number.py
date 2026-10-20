from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import zones
from .const import DOMAIN
from .helpers import UserConfigEntity, ZoneEntity, snake, zone_translation
from .shared import Shared

# what the V-ZUG app offers first when a timed function is switched on
DEFAULT_BOOST_HOURS = 12.0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared: Shared = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[NumberEntity] = []

    for category in shared.config_coord.data.values():
        for command in category.commands.values():
            if command.get("type") == "range" and command.get("alterable", True):
                entities.append(
                    UserConfig(
                        shared,
                        category_key=category.key,
                        command_key=command.get("command", ""),
                    )
                )

    entities.extend(_zone_entities(shared))
    async_add_entities(entities)


def _zone_entities(shared: Shared) -> list[NumberEntity]:
    if shared.zone_coord is None:
        return []
    zone_map = shared.zone_coord.data.zones
    entities: list[NumberEntity] = [
        ZoneTemperature(shared, zone=zone)
        for zone in zones.zones_with(zone_map, zones.TEMP_KEY)
    ]
    for key in zones.BOOST_KEYS:
        entities.extend(
            BoostDuration(shared, zone=zone, key=key)
            for zone in zones.zones_with(zone_map, key)
        )
    if party_zones := zones.zones_with(zone_map, zones.PARTY_KEY):
        entities.append(BoostDuration(shared, zone=party_zones[0], key=zones.PARTY_KEY))
    entities.extend(
        Timer(shared, zone=zone)
        for zone in zones.zones_with(zone_map, zones.TIMER_KEY)
        if zones.is_timer_zone(zone)
    )
    return entities


class ZoneTemperature(ZoneEntity, NumberEntity):
    """The set temperature of a zone. The appliance reports no measured value."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1.0

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key=zones.TEMP_KEY)
        self._attr_translation_key, name = zone_translation("temperature", zone)
        if name:
            self._attr_name = name

    @property
    def native_unit_of_measurement(self) -> str:
        return zones.temperature_unit(self.coordinator.data.modes)

    @property
    def native_min_value(self) -> float:
        return float(zones.value_field(self.zone_data, self.vzug_key, "min") or 0)

    @property
    def native_max_value(self) -> float:
        return float(zones.value_field(self.zone_data, self.vzug_key, "max") or 0)

    @property
    def native_value(self) -> float | None:
        value = zones.value_field(self.zone_data, self.vzug_key, "set")
        return float(value) if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        await self._write_zone(zones.format_value(value))


class BoostDuration(ZoneEntity, RestoreNumber):
    """How long SuperCool / SuperFreeze / PartyCooling run when switched on.

    Kept by Home Assistant, the appliance has no such setting: the duration is
    sent along with the 'on' command. Changing it while the function runs does
    not change the running one.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_native_min_value = 1.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.BOX

    def __init__(self, shared: Shared, *, zone: str, key: str) -> None:
        super().__init__(shared, zone=zone, key=key)
        self._attr_unique_id = f"{shared.unique_id_prefix}-boost-duration-{key}"
        self._attr_translation_key = f"duration_{snake(key)}"
        shared.boost_hours.setdefault(
            key, min(DEFAULT_BOOST_HOURS, self.native_max_value)
        )

    @property
    def available(self) -> bool:
        return True

    @property
    def native_max_value(self) -> float:
        seconds = zones.value_field(self.zone_data, self.vzug_key, "max")
        return float(seconds) / 3600 if isinstance(seconds, (int, float)) else 24.0

    @property
    def native_value(self) -> float:
        return self.shared.boost_hours[self.vzug_key]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value:
            self.shared.boost_hours[self.vzug_key] = last.native_value

    async def async_set_native_value(self, value: float) -> None:
        self.shared.boost_hours[self.vzug_key] = value
        self.async_write_ha_state()


class Timer(ZoneEntity, NumberEntity):
    """The appliance's kitchen timer: minutes left, set a value to (re)start it.

    0 stops it.
    """

    _attr_translation_key = "timer"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-outline"

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key=zones.TIMER_KEY)

    @property
    def native_max_value(self) -> float:
        seconds = zones.value_field(self.zone_data, self.vzug_key, "max")
        return float(seconds) // 60 if isinstance(seconds, (int, float)) else 595.0

    @property
    def native_value(self) -> float:
        left = zones.remaining_seconds(self.zone_data, self.vzug_key)
        # round up, so a timer about to ring still shows 1 and not 0
        return float(-(-left // 60)) if left else 0.0

    async def async_set_native_value(self, value: float) -> None:
        await self._write_zone(zones.format_value(int(value) * 60))


class UserConfig(NumberEntity, UserConfigEntity):
    _attr_mode = NumberMode.SLIDER

    @property
    def native_min_value(self) -> float:
        try:
            return float(self.vzug_command["minMax"][0])
        except (ValueError, LookupError, TypeError):
            return 0.0

    @property
    def native_max_value(self) -> float:
        try:
            return float(self.vzug_command["minMax"][1])
        except (ValueError, LookupError, TypeError):
            return 0.0

    @property
    def native_step(self) -> float | None:
        return 1.0

    @property
    def native_value(self) -> float | None:
        value = self.vzug_command.get("value")
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self.shared.client.set_command(self.vzug_command_key, str(int(value)))
        await self.coordinator.async_request_refresh()
