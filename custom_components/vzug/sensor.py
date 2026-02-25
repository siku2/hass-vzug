from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import api
from .coordinator import ProgramCoordinator, Shared, StateCoordinator
from .entity import UserConfigEntity

if TYPE_CHECKING:
    from . import VZugConfigEntry

PARALLEL_UPDATES = 0

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
        # This is tricky, because it is not really a measurement, but calculated by the device.
        # But HomeAssistant does not like that combination. It prevents SensorDeviceClass.WATER with SensorStateClass.MEASUREMENT
        # Therefore we do not set the device class here.
        "water.average",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
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
        entity_registry_enabled_default=False,
        native_unit_of_measurement="kWh",
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="energy_average",
    ),
    SensorEntityDescription(
        "water.option",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        native_unit_of_measurement="L",
        state_class=SensorStateClass.TOTAL_INCREASING,
        translation_key="water_option",
    ),
]


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
        ActiveErrors(shared),
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

    for door_key, door_data in (
        shared.state_coord.data.eco_info.get("doorOpenings") or {}
    ).items():
        for period, period_data in door_data.items():
            for field in ("amount", "duration"):
                if field not in period_data:
                    continue
                entities.append(
                    DoorOpeningEco(
                        shared,
                        door_key=door_key,
                        period=period,
                        field=field,
                    )
                )

    if shared.program_coord is not None:
        for zone in shared.program_coord.data.zones:
            zone_name = zone.get("zone", "")
            if "temp" in zone:
                entities.append(
                    ZoneTemperature(shared, zone_name=zone_name, field="act")
                )
                entities.append(
                    ZoneTemperature(shared, zone_name=zone_name, field="set")
                )

    async_add_entities(entities)


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
            # 1. Resolve numeric program IDs to human-readable names
            try:
                return api.PROGRAM_NAMES.get(int(program), program)
            except (ValueError, TypeError):
                pass
            # 2. Try active zone program ID (e.g. oven cooking chamber)
            if self.shared.program_coord is not None:
                for zone in self.shared.program_coord.data.zones:
                    if zone.get("status") == "active" and "id" in zone:
                        name = api.PROGRAM_NAMES.get(zone["id"])
                        if name:
                            return name
            # 3. Translate known firmware text (e.g. German → English)
            return api.translate_device_text(program)
        elif device.get("Inactive") == "true":
            return "standby"
        else:
            return "active"


class ProgramEndRaw(StateBase):
    _attr_translation_key = "program_end_raw"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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
        status = self.coordinator.data.device.get("Status")
        if not status:
            return None
        return api.translate_status_text(status.strip())


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


_DOOR_OPENING_PERIOD_ENABLED: dict[str, bool] = {
    "today": True,
    "7DayAvg": False,
    "30DayAvg": False,
}


class DoorOpeningEco(StateBase):
    def __init__(
        self,
        shared: Shared,
        *,
        door_key: str,
        period: str,
        field: str,
    ) -> None:
        self._attr_translation_key = f"{door_key}_openings_{period}_{field}"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = _DOOR_OPENING_PERIOD_ENABLED.get(
            period, False
        )
        if field == "duration":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = "s"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        super().__init__(shared)
        self.vzug_door_key = door_key
        self.vzug_period = period
        self.vzug_field = field

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        try:
            return self.coordinator.data.eco_info["doorOpenings"][self.vzug_door_key][
                self.vzug_period
            ][self.vzug_field]
        except (LookupError, TypeError):
            return None


class ZoneTemperature(SensorEntity, CoordinatorEntity[ProgramCoordinator]):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"

    def __init__(
        self,
        shared: Shared,
        *,
        zone_name: str,
        field: str,
    ) -> None:
        assert shared.program_coord is not None
        super().__init__(shared.program_coord)
        self.shared = shared
        self.vzug_zone_name = zone_name
        self.vzug_field = field

        if field == "set":
            self._attr_translation_key = f"temperature_set_{zone_name}"
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        else:
            self._attr_translation_key = f"temperature_{zone_name}"
            self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-sensor-{self.translation_key}"
        )
        self._attr_device_info = shared.device_info

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        for zone in self.coordinator.data.zones:
            if zone.get("zone") == self.vzug_zone_name:
                try:
                    return zone["temp"][self.vzug_field]
                except (LookupError, TypeError):
                    return None
        return None


class ActiveErrors(StateBase):
    _attr_translation_key = "active_errors"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        hh_status = self.coordinator.data.hh_device_status
        errors = hh_status.get("errors", [])
        displayed_errors = hh_status.get("displayedErrors", [])
        return len(errors) + len(displayed_errors)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        hh_status = self.coordinator.data.hh_device_status
        return {
            "errors": hh_status.get("errors", []),
            "displayed_errors": hh_status.get("displayedErrors", []),
        }


class UserConfigSensor(SensorEntity, UserConfigEntity):
    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self.vzug_command.get("value")
