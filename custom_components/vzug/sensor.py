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
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import api, zones
from .const import DOMAIN
from .helpers import UserConfigEntity, ZoneEntity, snake
from .shared import Shared, StateCoordinator

# https://developers.home-assistant.io/docs/core/entity/sensor/

_ECO_SENSORS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        "water.total",
        device_class=SensorDeviceClass.WATER,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:water",
        native_unit_of_measurement="L",
        state_class=SensorStateClass.TOTAL,
        translation_key="water_total",
    ),
    SensorEntityDescription(
        "water.program",
        device_class=SensorDeviceClass.WATER,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:water",
        native_unit_of_measurement="L",
        state_class=SensorStateClass.TOTAL_INCREASING,
        translation_key="water_program",
    ),
    SensorEntityDescription(
        "energy.total",
        device_class=SensorDeviceClass.ENERGY,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:lightning-bolt",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.TOTAL,
        translation_key="energy_total",
    ),
    SensorEntityDescription(
        "energy.program",
        device_class=SensorDeviceClass.ENERGY,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:lightning-bolt",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.TOTAL_INCREASING,
        translation_key="energy_program",
    ),
    SensorEntityDescription(
        # This is tricky, because it is not really a measurement, but calculated by the device.
        # But HomeAssistant does not like that combination. It prevents SensorDeviceClass.WATER with SensorStateClass.MEASUREMENT
        # Therefore we do not set the device class here.
        "water.average",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:water",
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
        icon="mdi:lightning-bolt",
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="energy_average",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared: Shared = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SensorEntity] = [
        Program(shared),
        ProgramEnd(shared),
        ProgramEndRaw(shared),
        Status(shared),
        LastNotification(shared),
    ]

    for category in shared.config_coord.data.values():
        for command in category.commands.values():
            if command.get("type") == "status":
                entities.append(
                    UserConfigSensor(
                        shared,
                        category_key=category.key,
                        command_key=command.get("command", ""),
                    )
                )

    for desc in _ECO_SENSORS:
        category, _, field = desc.key.partition(".")
        if category not in shared.state_coord.data.eco_info:
            continue
        entities.append(Eco(shared, desc, category=category, field=field))

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
    return entities


class TimeLeft(ZoneEntity, SensorEntity):
    """Minutes left of a running SuperCool / SuperFreeze / PartyCooling, else 0."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-sand"

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


class StateBase(SensorEntity, CoordinatorEntity[StateCoordinator]):
    _attr_has_entity_name = True

    shared: Shared

    def __init__(self, shared: Shared) -> None:
        super().__init__(shared.state_coord)
        self.shared = shared

        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-sensor-{self.translation_key}"
        )
        self._attr_device_info = shared.device_info


class Program(StateBase):
    _attr_translation_key = "program"

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        device = self.coordinator.data.device
        if program := device.get("Program"):
            return program
        elif device.get("Inactive") == "true":
            return "standby"
        else:
            return "active"


class ProgramEndRaw(StateBase):
    _attr_translation_key = "program_end_raw"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
    _attr_icon = "mdi:bell"

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
    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self.vzug_command.get("value")
