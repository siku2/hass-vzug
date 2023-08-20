import re
from collections.abc import Callable, Iterator, Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import Coordinator, DeviceCategory, api
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Coordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SensorEntity] = [
        Program(coordinator),
        ProgramEnd(coordinator),
        ProgramEndRaw(coordinator),
        Status(coordinator),
        LastNotification(coordinator),
    ]

    if coordinator.category == DeviceCategory.ADORA_DISH:
        entities.extend(_adoradish_entities(coordinator))
    if coordinator.category == DeviceCategory.ADORA_WASH:
        entities.extend(_adorawash_entities(coordinator))

    async_add_entities(entities)


def _adoradish_entities(coordinator: Coordinator) -> Iterator[SensorEntity]:
    for key, state_class in (
        ("PROGRAM", SensorStateClass.MEASUREMENT),
        ("AVG", SensorStateClass.MEASUREMENT),
        ("TOTAL", SensorStateClass.TOTAL_INCREASING),
    ):
        lower_key = key.lower()
        device_class = (
            None
            if state_class == SensorStateClass.MEASUREMENT
            else SensorDeviceClass.ENERGY
        )
        yield UserSettingsSensor(
            coordinator,
            SensorEntityDescription(
                key=f"energy_{lower_key}",
                device_class=device_class,
                translation_key=f"energy_{lower_key}",
                native_unit_of_measurement="kWh",
                state_class=state_class,
            ),
            command=f"ECO_MGMT_ENERGY_{key}",
            extractor=lambda value: _extract_nth_number(value["value"], 0),
        )

    for key, state_class in (
        ("PROGRAM", SensorStateClass.MEASUREMENT),
        ("AVG", SensorStateClass.MEASUREMENT),
        ("TOTAL", SensorStateClass.TOTAL_INCREASING),
    ):
        lower_key = key.lower()
        device_class = (
            None
            if state_class == SensorStateClass.MEASUREMENT
            else SensorDeviceClass.WATER
        )
        yield UserSettingsSensor(
            coordinator,
            SensorEntityDescription(
                key=f"water_{lower_key}",
                device_class=device_class,
                translation_key=f"water_{lower_key}",
                native_unit_of_measurement="L",
                state_class=state_class,
            ),
            command=f"ECO_MGMT_WATER_{key}",
            extractor=lambda value: _extract_nth_number(value["value"], 0),
        )


def _adorawash_entities(coordinator: Coordinator) -> Iterator[SensorEntity]:
    def extract_energy(value: api.CommandValue) -> float | None:
        energy = _extract_nth_number(value["value"], 0)
        if energy == 0.1:
            # the API sometimes returns <0,1
            raise NoUpdate()
        return energy

    yield UserSettingsSensor(
        coordinator,
        SensorEntityDescription(
            key="energy_total",
            device_class=SensorDeviceClass.ENERGY,
            translation_key="energy_total",
            native_unit_of_measurement="kWh",
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        command="ecomXstatXtotal",
        extractor=extract_energy,
    )

    yield UserSettingsSensor(
        coordinator,
        SensorEntityDescription(
            key="energy_avg",
            device_class=None,  # can't use ENERGY because it doesn't support MEASUREMENT
            translation_key="energy_avg",
            native_unit_of_measurement="kWh",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        command="ecomXstatXavarage",
        extractor=extract_energy,
    )

    def extract_water(value: api.CommandValue) -> float | None:
        water = _extract_nth_number(value["value"], 1)
        if water == 0:
            # the API sometimes returns <0,
            raise NoUpdate()
        return water

    yield UserSettingsSensor(
        coordinator,
        SensorEntityDescription(
            key="water_total",
            device_class=SensorDeviceClass.WATER,
            translation_key="water_total",
            native_unit_of_measurement="L",
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        command="ecomXstatXtotal",
        extractor=extract_water,
    )

    yield UserSettingsSensor(
        coordinator,
        SensorEntityDescription(
            key="water_avg",
            device_class=None,  # can't use WATER because it doesn't support MEASUREMENT
            translation_key="water_avg",
            native_unit_of_measurement="L",
            state_class=SensorStateClass.MEASUREMENT,
        ),
        command="ecomXstatXavarage",
        extractor=extract_water,
    )


_RE_NUMBER = re.compile(r"\d[\d,.]*")


def _extract_numbers(text: str) -> Iterator[float]:
    for match in _RE_NUMBER.finditer(text):
        raw = match.group(0)
        raw = raw.replace(",", ".")
        try:
            yield float(raw)
        except ValueError:
            continue


def _extract_nth_number(text: str, index: int) -> float:
    num_it = _extract_numbers(text)
    try:
        for _ in range(index):
            next(num_it)
        return next(num_it)
    except StopIteration:
        raise NoUpdate() from None


class Base(SensorEntity, CoordinatorEntity[Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: Coordinator, context: Any = None) -> None:
        super().__init__(coordinator, context)
        self._attr_unique_id = (
            f"{coordinator.unique_id_prefix}-sensor-{self.translation_key}"
        )
        self._attr_device_info = coordinator.device_info


class Program(Base):
    _attr_translation_key = "program"

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        device = self.coordinator.data.device
        if device is None:
            return None
        if device["Inactive"] == "true":
            return "standby"
        return device["Program"]


class ProgramEndRaw(Base):
    _attr_translation_key = "program_end_raw"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def vzug_program_end(self) -> api.DeviceStatusProgramEnd | None:
        device = self.coordinator.data.device
        if device is None:
            return None
        program_end = device.get("ProgramEnd")
        if not program_end:
            return None

        return program_end

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        if program_end := self.vzug_program_end:
            return program_end["End"]
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        end_type = None
        if program_end := self.vzug_program_end:
            end_type = program_end["EndType"]
        return {"type": end_type}


_RE_END_DURATON = re.compile(r"(?P<hours>\d+)[h](?P<minutes>\d+)", re.IGNORECASE)


class ProgramEnd(ProgramEndRaw):
    _attr_translation_key = "program_end"
    _attr_entity_category = None
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: Coordinator, context: Any = None) -> None:
        super().__init__(coordinator, context)
        self.__end_at = None

    @property
    def vzug_program_duration_left(self) -> timedelta | None:
        end = None
        if program_end := self.vzug_program_end:
            end = program_end["End"]
        if not end:
            return None

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
        end_at = self.coordinator.data.fetched_at + remaining
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
            # neiter is None, only update if more than 10 minutes apart
            if abs(end_at - self.__end_at) > timedelta(minutes=10):
                self.__end_at = end_at

        self.async_write_ha_state()


class Status(Base):
    _attr_translation_key = "status"

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        device = self.coordinator.data.device
        if device is None:
            return None
        return device["Status"] or None


class LastNotification(Base):
    _attr_translation_key = "last_notification"
    _attr_icon = "mdi:bell"

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        notifications = self.coordinator.data.notifications
        try:
            return notifications[0]["message"]
        except (IndexError, KeyError):
            return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        try:
            last_notification_date = self.coordinator.data.notifications[0]["date"]
        except (IndexError, KeyError):
            last_notification_date = None

        return {"timestamp": last_notification_date}


ValueExtractorFn = Callable[[api.CommandValue], StateType | date | datetime | Decimal]


class UserSettingsSensor(SensorEntity):
    coordinator: Coordinator
    command: str
    extractor: ValueExtractorFn

    __value: StateType | date | datetime | Decimal

    def __init__(
        self,
        coordinator: Coordinator,
        entity_description: SensorEntityDescription,
        *,
        command: str,
        extractor: ValueExtractorFn,
    ) -> None:
        super().__init__()

        self.entity_description = entity_description

        self._attr_has_entity_name = True
        self._attr_unique_id = (
            f"{coordinator.unique_id_prefix}-sensor-{entity_description.key}"
        )
        self._attr_device_info = coordinator.device_info

        self.coordinator = coordinator
        self.command = command
        self.extractor = extractor
        self.__value = None

    async def async_update(self) -> None:
        command_value = await self.coordinator.api.get_command(self.command)
        try:
            new_value = self.extractor(command_value)
        except NoUpdate:
            return

        self.__value = new_value

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        return self.__value


class NoUpdate(Exception):
    ...
