from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import zones
from .entity import UserConfigEntity, vzug_action, VZugEntity, ZoneEntity
from .helpers import snake, zone_translation
from .coordinator import ProgramCoordinator, Shared, VZugConfigEntry

# what the V-ZUG app offers first when a timed function is switched on
DEFAULT_BOOST_HOURS = 12.0


# the appliance handles one request at a time, so do the actions
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VZugConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared = config_entry.runtime_data

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
    if shared.program_coord is not None and shared.program_zone is None:
        entities.append(StartDelay(shared))
    elif shared.program_coord is not None:
        entities.extend(
            ProgramSetting(shared, key=key) for key in zones.PROGRAM_SETTINGS
        )
    async_add_entities(entities)


class ProgramSetting(VZugEntity[ProgramCoordinator], NumberEntity):
    """Temperature or duration sent with the next oven program.

    Kept by Home Assistant until 'Send to appliance'. The limits are those of
    the selected program; a value outside them is not sent.
    """

    _attr_mode = NumberMode.BOX

    def __init__(self, shared: Shared, *, key: str) -> None:
        assert shared.program_coord is not None
        super().__init__(
            shared, shared.program_coord, unique_id_suffix=f"program-setting-{key}"
        )
        self.vzug_key = key
        if key == "temp":
            self._attr_translation_key = "program_temperature"
            self._attr_device_class = NumberDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        else:
            self._attr_translation_key = "program_duration"
            self._attr_device_class = NumberDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES

    @property
    def available(self) -> bool:
        return True

    def _field(self, field: str) -> float | None:
        data = self.coordinator.data
        value = zones.value_field(data.current if data else None, self.vzug_key, field)
        if not isinstance(value, (int, float)):
            return None
        return value / 60 if self.vzug_key == "duration" else float(value)

    @property
    def native_min_value(self) -> float:
        return self._field("min") or 0.0

    @property
    def native_max_value(self) -> float:
        return self._field("max") or (300.0 if self.vzug_key == "temp" else 1440.0)

    @property
    def native_step(self) -> float:
        return self._field("step") or 1.0

    @property
    def native_value(self) -> float | None:
        wanted = self.shared.program_settings.get(self.vzug_key)
        if wanted is None:
            return self._field("set")
        return wanted / 60 if self.vzug_key == "duration" else wanted

    @vzug_action
    async def async_set_native_value(self, value: float) -> None:
        self.shared.program_settings[self.vzug_key] = (
            value * 60 if self.vzug_key == "duration" else value
        )
        self.async_write_ha_state()


class StartDelay(VZugEntity[ProgramCoordinator], NumberEntity):
    """Delayed start for the next 'Send to appliance', in hours. 0 starts right away.

    Kept by Home Assistant until the program is sent, then sent as 'starttime'
    and reset to 0. The countdown begins once the door is closed.
    """

    _attr_translation_key = "start_delay"
    _attr_icon = "mdi:clock-start"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_native_min_value = 0.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.BOX

    def __init__(self, shared: Shared) -> None:
        assert shared.program_coord is not None
        super().__init__(shared, shared.program_coord, unique_id_suffix="start-delay")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_max_value(self) -> float:
        data = self.coordinator.data
        return zones.start_delay_max_hours(data.current if data else None)

    @property
    def native_value(self) -> float:
        return self.shared.start_delay_hours

    @vzug_action
    async def async_set_native_value(self, value: float) -> None:
        self.shared.start_delay_hours = value
        self.async_write_ha_state()


def _zone_entities(shared: Shared) -> list[NumberEntity]:
    if shared.zone_coord is None:
        return []
    zone_map = shared.zone_coord.data.zones
    entities: list[NumberEntity] = [
        ZoneTemperature(shared, zone=zone)
        for zone in zones.zones_with(zone_map, zones.TEMP_KEY)
        # an oven's temperature belongs to its program
        if not zones.is_oven_zone(zone, zone_map[zone])
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
    if zones.ILLUMINATION_MODE in shared.zone_coord.data.modes:
        entities.append(Illumination(shared))
    entities.extend(
        WarmingDrawerDuration(shared, zone=zone)
        for zone in zone_map
        if zones.is_warming_drawer(zone) and shared.client.hh_supports((1, 5, 0))
    )
    return entities


class Illumination(ZoneEntity, NumberEntity):
    """Interior light of a wine cabinet, 0 (off) to 5."""

    _attr_translation_key = "illumination"
    _attr_icon = "mdi:lightbulb-on-outline"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 5.0
    _attr_native_step = 1.0
    _attr_mode = NumberMode.SLIDER

    def __init__(self, shared: Shared) -> None:
        super().__init__(shared, zone="", key=zones.ILLUMINATION_MODE)

    @property
    def native_value(self) -> float | None:
        try:
            return float(self.coordinator.data.modes.get(self.vzug_key, ""))
        except ValueError:
            return None

    @vzug_action
    async def async_set_native_value(self, value: float) -> None:
        await self.shared.client.set_cmd_value(self.vzug_key, str(int(value)))
        await self.coordinator.async_request_refresh()


class WarmingDrawerDuration(ZoneEntity, NumberEntity):
    """How long the warming drawer runs when started, in minutes.

    Kept by Home Assistant until 'Start warming drawer' sends it.
    """

    _attr_translation_key = "warming_drawer_duration"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key=zones.TIMER_KEY)
        self._attr_unique_id = f"{shared.unique_id_prefix}-zone-{zone}-duration-setting"
        seconds = zones.value_field(self.zone_data, self.vzug_key, "set") or 7200
        shared.warming_drawer_minutes.setdefault(zone, seconds // 60)

    def _limit(self, field: str, default: float) -> float:
        seconds = zones.value_field(self.zone_data, self.vzug_key, field)
        return seconds / 60 if isinstance(seconds, (int, float)) else default

    @property
    def available(self) -> bool:
        return True

    @property
    def native_min_value(self) -> float:
        return self._limit("min", 30)

    @property
    def native_max_value(self) -> float:
        return self._limit("max", 720)

    @property
    def native_step(self) -> float:
        return max(self._limit("step", 60), 1)

    @property
    def native_value(self) -> float:
        return self.shared.warming_drawer_minutes[self.vzug_zone]

    @vzug_action
    async def async_set_native_value(self, value: float) -> None:
        self.shared.warming_drawer_minutes[self.vzug_zone] = value
        self.async_write_ha_state()


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

    @vzug_action
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

    @vzug_action
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

    @vzug_action
    async def async_set_native_value(self, value: float) -> None:
        if any(zones.is_cooling_zone(z) for z in self.coordinator.data.zones):
            # refrigerators: {"zone":"countdown1","duration":"600"}, "0" stops it
            await self._write_zone(zones.format_value(int(value) * 60))
            return
        # ovens, like the V-ZUG app: start with status active, stop like a program
        if value <= 0:
            await self.shared.client.stop_program(self.vzug_zone)
        else:
            await self.shared.client.set_program_dto(
                {
                    "zone": self.vzug_zone,
                    "id": zones.TIMER_PROGRAM,
                    "status": "active",
                    "duration": int(value) * 60,
                }
            )
        await self.coordinator.async_request_refresh()


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

    @vzug_action
    async def async_set_native_value(self, value: float) -> None:
        await self.shared.client.set_command(self.vzug_command_key, str(int(value)))
        await self.coordinator.async_request_refresh()
