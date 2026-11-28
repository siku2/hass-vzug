import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import api, zones
from .coordinator import (
    ProgramCoordinator,
    Shared,
    StateCoordinator,
    UpdateCoordinator,
    VZugConfigEntry,
)
from .entity import UserConfigEntity, VZugEntity, ZoneEntity, user_config_entities
from .helpers import snake, zone_translation

# https://developers.home-assistant.io/docs/core/entity/sensor/

_ECO_SENSORS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        "water.total",
        device_class=SensorDeviceClass.WATER,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="L",
        state_class=SensorStateClass.TOTAL,
        translation_key="water_total",
    ),
    SensorEntityDescription(
        "water.program",
        device_class=SensorDeviceClass.WATER,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="L",
        state_class=SensorStateClass.TOTAL_INCREASING,
        translation_key="water_program",
    ),
    SensorEntityDescription(
        "energy.total",
        device_class=SensorDeviceClass.ENERGY,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.TOTAL,
        translation_key="energy_total",
    ),
    SensorEntityDescription(
        "energy.program",
        device_class=SensorDeviceClass.ENERGY,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.TOTAL_INCREASING,
        translation_key="energy_program",
    ),
    SensorEntityDescription(
        "energy.lastMonth",
        device_class=SensorDeviceClass.ENERGY,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.TOTAL,
        translation_key="energy_last_month",
    ),
    SensorEntityDescription(
        "energy.lastYear",
        device_class=SensorDeviceClass.ENERGY,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.TOTAL,
        translation_key="energy_last_year",
    ),
    SensorEntityDescription(
        # This is tricky, because it is not really a measurement, but calculated by the device.
        # But HomeAssistant does not like that combination. It prevents SensorDeviceClass.WATER with SensorStateClass.MEASUREMENT
        # Therefore we do not set the device class here.
        "water.average",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="L",
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="water_average",
    ),
    SensorEntityDescription(
        # This is tricky, because it is not really a measurement, but calculated by the device.
        # But HomeAssistant does not like that combination. It prevents SensorDeviceClass.ENERGY with SensorStateClass.MEASUREMENT
        # Therefore we do not set the device class here.
        "energy.average",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="energy_average",
    ),
]


PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VZugConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared = config_entry.runtime_data

    entities: list[SensorEntity] = [
        Program(shared),
        ProgramEnd(shared),
        ProgramEndRaw(shared),
        Status(shared),
        LastNotification(shared),
    ]
    if shared.client.hh_supports((1, 2, 0)):
        entities.append(ZhMode(shared))
    if shared.meta.supports_cloud_status():
        entities.append(CloudStatus(shared))
    if shared.program_coord is not None:
        entities.extend(
            ProgramInfo(shared, shared.program_coord, zone="", kind=kind)
            for kind in ProgramInfo.KINDS
        )

    entities.extend(
        user_config_entities(
            shared,
            async_add_entities,
            lambda c: c.get("type") == "status",
            UserConfigSensor,
        )
    )

    eco_info = shared.state_coord.data.eco_info
    for desc in _ECO_SENSORS:
        category, _, field = desc.key.partition(".")
        if category not in eco_info:
            continue
        if field in ("lastMonth", "lastYear") and field not in eco_info[category]:
            continue
        entities.append(Eco(shared, desc, category=category, field=field))
    for index, _ in enumerate(eco_info.get("doorOpenings") or []):
        entities.extend(
            DoorOpenings(shared, index=index, period=period)
            for period in DoorOpenings.PERIODS
        )
    if shared.program_coord is not None:
        entities.extend(
            ProgramValue(shared, key=key)
            for key in zones.PROGRAM_VALUES.get(shared.meta.machine_type, ())
        )

    entities.extend(_zone_entities(shared))
    async_add_entities(entities)


def _zone_entities(shared: Shared) -> list[SensorEntity]:
    if shared.zone_coord is None:
        return []
    data = shared.zone_coord.data
    entities: list[SensorEntity] = []
    for key in zones.BOOST_KEYS:
        entities.extend(
            TimeLeft(shared, zone=zone, key=key)
            for zone in zones.zones_with(data.zones, key)
        )
    if party_zones := zones.zones_with(data.zones, zones.PARTY_KEY):
        entities.append(TimeLeft(shared, zone=party_zones[0], key=zones.PARTY_KEY))
    entities.extend(
        ModeSensor(shared, mode=mode)
        for mode in zones.SENSOR_MODES
        if mode in data.modes
    )
    # zones running programs (ovens, warming drawers, hobs); a fridge zone is
    # always 'active' and has no end
    for zone, zone_data in data.zones.items():
        if not zones.is_program_zone(zone):
            continue
        entities.extend(
            ProgramInfo(shared, shared.zone_coord, zone=zone, kind=kind)
            for kind in ProgramInfo.KINDS
        )
        if zones.is_hob_zone(zone):
            entities.append(HobLevel(shared, zone=zone))
        if zones.is_oven_zone(zone, zone_data):
            entities.extend(
                OvenValue(shared, zone=zone, key=key, field=field)
                for key, field in OvenValue.VALUES
            )
    return entities


class HobLevel(ZoneEntity, SensorEntity):
    """Power level of a hob zone, in steps of 0.5. Read only."""

    _attr_translation_key = "hob_level"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key="level")
        self._attr_translation_placeholders = {"zone": zones.hob_zone_letter(zone)}

    @property
    def native_value(self) -> StateType:
        return zones.value(self.zone_data, self.vzug_key)


class OvenValue(ZoneEntity, SensorEntity):
    """A reading of the cooking chamber. Values only show while a program runs."""

    # (key, field) -> translation key
    VALUES = {
        ("temp", "act"): "cavity_temperature",
        ("temp", "set"): "cavity_target_temperature",
        ("probetemp", "act"): "probe_temperature",
        ("probetemp", "set"): "probe_target_temperature",
        ("preheatStatus", "act"): "preheat_status",
        ("doorStatus", "act"): "door_status",
    }

    def __init__(self, shared: Shared, *, zone: str, key: str, field: str) -> None:
        super().__init__(shared, zone=zone, key=key)
        self.vzug_field = field
        self._attr_unique_id = f"{shared.unique_id_prefix}-zone-{zone}-{key}-{field}"
        self._attr_translation_key = self.VALUES[(key, field)]
        if key in ("temp", "probetemp"):
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> StateType:
        return zones.value_field(self.zone_data, self.vzug_key, self.vzug_field)


class ProgramInfo(VZugEntity[Any], SensorEntity):
    """State, end or start of the program in one zone, from 'getProgram'.

    For dishwashers and washers (no zones) this reads the program coordinator.
    """

    KINDS = ("program_state", "program_end_time", "program_start_time")

    def __init__(
        self, shared: Shared, coordinator: Any, *, zone: str, kind: str
    ) -> None:
        super().__init__(
            shared, coordinator, unique_id_suffix=f"program-{zone or 'main'}-{kind}"
        )
        self.vzug_zone = zone
        self.vzug_kind = kind
        if zone:
            self._attr_translation_key, name = zone_translation(kind, zone)
            if name:
                self._attr_name = name
        else:
            self._attr_translation_key = kind
        if kind == "program_state":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(zones.PROGRAM_STATES)
            if self._attr_translation_key is None:
                # no translation to take the icon from, see icons.json
                self._attr_icon = "mdi:state-machine"
        else:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def _program(self) -> Mapping[str, Any] | None:
        data = self.coordinator.data
        if data is None:
            return None
        if self.vzug_zone:
            return data.zones.get(self.vzug_zone)
        return data.current

    @property
    def native_value(self) -> str | datetime | None:
        program = self._program
        fetched_at = self.coordinator.data.fetched_at if program is not None else None
        if self.vzug_kind == "program_state":
            # the program coordinator only keeps a program while one is selected
            status = (program or {}).get(
                "status", "idle" if not self.vzug_zone else None
            )
            return status if status in zones.PROGRAM_STATES else None
        if program is None:
            return None
        if self.vzug_kind == "program_end_time":
            return zones.end_time(program, fetched_at)
        return zones.start_time(program, fetched_at)


class TimeLeft(ZoneEntity, SensorEntity):
    """Minutes left of a running SuperCool / SuperFreeze / PartyCooling, else 0."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, shared: Shared, *, zone: str, key: str) -> None:
        super().__init__(shared, zone=zone, key=key)
        self._attr_unique_id = f"{shared.unique_id_prefix}-zone-{zone}-{key}-left"
        self._attr_translation_key = f"time_left_{snake(key)}"

    @property
    def native_value(self) -> int:
        left = zones.remaining_seconds(self.zone_data, self.vzug_key)
        return -(-left // 60) if left else 0


class ModeSensor(ZoneEntity, SensorEntity):
    """A 'cmd' mode we only show, ex. Sabbath: switching it on turns off the
    appliance's alarms and buttons, which is not something to do remotely."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["on", "off"]

    def __init__(self, shared: Shared, *, mode: str) -> None:
        super().__init__(shared, zone="", key=mode)
        self._attr_translation_key = snake(mode)

    @property
    def native_value(self) -> str | None:
        on = zones.mode_is_on(self.coordinator.data.modes.get(self.vzug_key))
        return None if on is None else ("on" if on else "off")


class StateBase(SensorEntity, VZugEntity[StateCoordinator]):
    def __init__(self, shared: Shared) -> None:
        super().__init__(
            shared,
            shared.state_coord,
            unique_id_suffix=f"sensor-{self.translation_key}",
        )


class Program(StateBase):
    _attr_translation_key = "program"

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        device = self.coordinator.data.device
        if program := device.get("Program"):
            return program
        if device.get("Inactive") == "true":
            return "standby"
        return "active"


class ProgramEndRaw(StateBase):
    _attr_translation_key = "program_end_raw"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # 'Program end' shows the same as a timestamp
    _attr_entity_registry_enabled_default = False

    @property
    def vzug_program_end(self) -> api.DeviceStatusProgramEnd:
        try:
            return self.coordinator.data.device["ProgramEnd"]
        except LookupError:
            return api.DeviceStatusProgramEnd()

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self.vzug_program_end.get("End")

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        return {"type": self.vzug_program_end.get("EndType")}


_RE_END_DURATON = re.compile(r"(?P<hours>\d+)[h](?P<minutes>\d+)", re.IGNORECASE)


class ProgramEnd(ProgramEndRaw):
    _attr_translation_key = "program_end"
    _attr_entity_category = None
    _attr_entity_registry_enabled_default = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, shared: Shared) -> None:
        super().__init__(shared)
        self.__end_at = None

    @property
    def vzug_program_duration_left(self) -> timedelta | None:
        end = self.vzug_program_end.get("End", "")
        re_match = _RE_END_DURATON.match(end)
        if not re_match:
            return None

        return timedelta(
            hours=int(re_match.group("hours")),
            minutes=int(re_match.group("minutes")),
        )

    @property
    def vzug_program_end_at(self) -> datetime | None:
        remaining = self.vzug_program_duration_left
        if not remaining:
            return None
        end_at = self.coordinator.data.device_fetched_at + remaining
        # subtract sub-minute because we don't have it anyways
        return end_at - timedelta(
            seconds=end_at.second, microseconds=end_at.microsecond
        )

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self.__end_at

    @callback
    def _handle_coordinator_update(self) -> None:
        end_at = self.vzug_program_end_at
        if end_at is None:
            self.__end_at = None
        elif self.__end_at is None:
            self.__end_at = end_at
        else:
            # neither is None, only update if more than 10 minutes apart
            if abs(end_at - self.__end_at) > timedelta(minutes=10):
                self.__end_at = end_at

        self.async_write_ha_state()


class Status(StateBase):
    _attr_translation_key = "status"

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        # 'or None' so we don't display empty strings
        return self.coordinator.data.device.get("Status") or None


class Eco(StateBase):
    def __init__(
        self,
        shared: Shared,
        desc: SensorEntityDescription,
        *,
        category: str,
        field: str,
    ) -> None:
        # needs to be set before StateBase.__init__ so it can access 'translation_key'
        self.entity_description = desc

        super().__init__(shared)
        self.vzug_category = category
        self.vzug_field = field

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        try:
            return self.coordinator.data.eco_info[cast(Any, self.vzug_category)][
                self.vzug_field
            ]
        except LookupError:
            return None


class LastNotification(StateBase):
    _attr_translation_key = "last_notification"

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        try:
            return self.coordinator.data.notifications[0]["message"]
        except LookupError:
            return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        try:
            last_notification_date = self.coordinator.data.notifications[0]["date"]
        except LookupError:
            last_notification_date = None

        return {"timestamp": last_notification_date}


class UserConfigSensor(SensorEntity, UserConfigEntity):
    """A read-only value from the settings, ex. 'Consumption last programme'.

    Disabled by default: most repeat a dedicated sensor (the eco values), as
    text the appliance formats for its display.
    """

    _attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self.vzug_command.get("value")


class ZhMode(StateBase):
    """The appliance's V-ZUG-Home setting, which decides whether it takes orders."""

    _attr_translation_key = "zh_mode"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "display", "operate"]

    @property
    def native_value(self) -> str | None:
        mode = self.coordinator.data.zh_mode
        return self._attr_options[mode] if mode in (0, 1, 2) else None


class CloudStatus(SensorEntity, VZugEntity[UpdateCoordinator]):
    """Connection to the V-ZUG cloud, '/ai getCloudStatus'."""

    _attr_translation_key = "cloud_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, shared: Shared) -> None:
        super().__init__(
            shared, shared.update_coord, unique_id_suffix="sensor-cloud_status"
        )

    @property
    def native_value(self) -> str | None:
        cloud = self.coordinator.data.cloud_status
        if not cloud:
            return None
        return cloud.get("status") if cloud.get("enabled", True) else "disabled"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        cloud = self.coordinator.data.cloud_status
        return {key: cloud.get(key) for key in ("enabled", "claimed")}


class DoorOpenings(StateBase):
    """How often a refrigerator door was opened, from 'getEcoInfo'."""

    PERIODS = ("today", "sevenDayAverage", "thirtyDayAverage")
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, shared: Shared, *, index: int, period: str) -> None:
        self._attr_translation_key = f"door_openings_{snake(period)}"
        super().__init__(shared)
        self.vzug_index = index
        self.vzug_period = period
        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-sensor-door-openings-{index}-{period}"
        )
        self._attr_translation_placeholders = {"door": str(index + 1)}
        # today's count is the interesting one, the averages are for statistics
        self._attr_entity_registry_enabled_default = period == "today"

    @property
    def native_value(self) -> StateType:
        try:
            entry = self.coordinator.data.eco_info["doorOpenings"][self.vzug_index]
            return entry[self.vzug_period]["amount"]
        except LookupError, TypeError:
            return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        try:
            entry = self.coordinator.data.eco_info["doorOpenings"][self.vzug_index]
            return {"duration": entry[self.vzug_period]["duration"]}
        except LookupError, TypeError:
            return None


class ProgramValue(VZugEntity[ProgramCoordinator], SensorEntity):
    """A reading of the selected program, ex. an OptiDos tray's fill level."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, shared: Shared, *, key: str) -> None:
        assert shared.program_coord is not None
        super().__init__(
            shared, shared.program_coord, unique_id_suffix=f"program-value-{key}"
        )
        self.vzug_key = key
        self._attr_translation_key = snake(key)

    @property
    def native_value(self) -> StateType:
        current = self.coordinator.data.current if self.coordinator.data else None
        value = zones.value(current, self.vzug_key)
        return value if isinstance(value, (str, int, float)) else None
