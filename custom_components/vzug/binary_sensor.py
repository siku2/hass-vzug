from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ProgramCoordinator, Shared

if TYPE_CHECKING:
    from . import VZugConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: "VZugConfigEntry",
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared = config_entry.runtime_data

    if shared.program_coord is None:
        return

    entities: list[BinarySensorEntity] = []
    for zone in shared.program_coord.data.zones:
        zone_name = zone.get("zone", "")
        if "doorClosed" in zone:
            entities.append(ZoneDoor(shared, zone_name=zone_name))

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
