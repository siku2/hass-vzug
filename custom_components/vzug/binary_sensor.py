from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ProgramCoordinator, Shared, StateCoordinator

if TYPE_CHECKING:
    from . import VZugConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: "VZugConfigEntry",
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared = config_entry.runtime_data

    entities: list[BinarySensorEntity] = []

    # Always add error tracking (all devices support hh getDeviceStatus)
    entities.append(HasErrors(shared))

    # Cloud connectivity (static, fetched once)
    entities.append(CloudConnected(shared))

    if shared.program_coord is not None:
        for zone in shared.program_coord.data.zones:
            zone_name = zone.get("zone", "")
            if "doorClosed" in zone:
                entities.append(ZoneDoor(shared, zone_name=zone_name))
            if "light" in zone:
                entities.append(ZoneLight(shared, zone_name=zone_name))
            if "preheatStatus" in zone:
                entities.append(ZonePreheat(shared, zone_name=zone_name))
            if "probeInserted" in zone:
                entities.append(ZoneProbeInserted(shared, zone_name=zone_name))

    async_add_entities(entities)


class ZoneDoor(BinarySensorEntity, CoordinatorEntity[ProgramCoordinator]):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, shared: Shared, *, zone_name: str) -> None:
        assert shared.program_coord is not None
        super().__init__(shared.program_coord)
        self.shared = shared
        self.vzug_zone_name = zone_name

        self._attr_translation_key = f"door_{zone_name}"
        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-binary_sensor-{self.translation_key}"
        )
        self._attr_device_info = shared.device_info

    @property
    def is_on(self) -> bool | None:
        for zone in self.coordinator.data.zones:
            if zone.get("zone") == self.vzug_zone_name:
                door_closed = zone.get("doorClosed")
                if door_closed is None:
                    return None
                return not door_closed
        return None


class ZoneLight(BinarySensorEntity, CoordinatorEntity[ProgramCoordinator]):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.LIGHT

    def __init__(self, shared: Shared, *, zone_name: str) -> None:
        assert shared.program_coord is not None
        super().__init__(shared.program_coord)
        self.shared = shared
        self.vzug_zone_name = zone_name

        self._attr_translation_key = f"light_{zone_name}"
        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-binary_sensor-{self.translation_key}"
        )
        self._attr_device_info = shared.device_info

    @property
    def is_on(self) -> bool | None:
        for zone in self.coordinator.data.zones:
            if zone.get("zone") == self.vzug_zone_name:
                light = zone.get("light")
                if light is None:
                    return None
                return light.get("set")
        return None


class ZonePreheat(BinarySensorEntity, CoordinatorEntity[ProgramCoordinator]):
    _attr_has_entity_name = True
    _attr_icon = "mdi:radiator"

    def __init__(self, shared: Shared, *, zone_name: str) -> None:
        assert shared.program_coord is not None
        super().__init__(shared.program_coord)
        self.shared = shared
        self.vzug_zone_name = zone_name

        self._attr_translation_key = f"preheat_{zone_name}"
        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-binary_sensor-{self.translation_key}"
        )
        self._attr_device_info = shared.device_info

    @property
    def is_on(self) -> bool | None:
        for zone in self.coordinator.data.zones:
            if zone.get("zone") == self.vzug_zone_name:
                preheat = zone.get("preheatStatus")
                if preheat is None:
                    return None
                return preheat.get("set", False)
        return None


class ZoneProbeInserted(BinarySensorEntity, CoordinatorEntity[ProgramCoordinator]):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(self, shared: Shared, *, zone_name: str) -> None:
        assert shared.program_coord is not None
        super().__init__(shared.program_coord)
        self.shared = shared
        self.vzug_zone_name = zone_name

        self._attr_translation_key = f"probe_{zone_name}"
        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-binary_sensor-{self.translation_key}"
        )
        self._attr_device_info = shared.device_info

    @property
    def is_on(self) -> bool | None:
        for zone in self.coordinator.data.zones:
            if zone.get("zone") == self.vzug_zone_name:
                probe = zone.get("probeInserted")
                if probe is None:
                    return None
                return probe.get("act", False)
        return None


class HasErrors(BinarySensorEntity, CoordinatorEntity[StateCoordinator]):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "has_errors"

    def __init__(self, shared: Shared) -> None:
        super().__init__(shared.state_coord)
        self.shared = shared

        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-binary_sensor-{self.translation_key}"
        )
        self._attr_device_info = shared.device_info

    @property
    def is_on(self) -> bool | None:
        hh_status = self.coordinator.data.hh_device_status
        errors = hh_status.get("errors", [])
        displayed_errors = hh_status.get("displayedErrors", [])
        return len(errors) > 0 or len(displayed_errors) > 0


class CloudConnected(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "cloud_connected"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, shared: Shared) -> None:
        self.shared = shared

        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-binary_sensor-{self.translation_key}"
        )
        self._attr_device_info = shared.device_info

    @property
    def is_on(self) -> bool | None:
        return self.shared.cloud_status.get("status") == "connected"
