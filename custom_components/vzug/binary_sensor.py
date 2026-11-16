from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import zones
from .const import DOMAIN
from .helpers import ZoneEntity, zone_translation
from .shared import Shared, StateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared: Shared = hass.data[DOMAIN][config_entry.entry_id]
    entities: list[BinarySensorEntity] = []
    if shared.client.hh_supports((1, 5, 0)):
        entities.append(Errors(shared))
    if shared.zone_coord is not None:
        entities.extend(
            Door(shared, zone=name)
            for name, zone in shared.zone_coord.data.zones.items()
            if isinstance(zone.get(zones.DOOR_KEY), bool)
        )
    async_add_entities(entities)


class Errors(CoordinatorEntity[StateCoordinator], BinarySensorEntity):
    """On while the appliance shows an error, the codes are attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "errors"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, shared: Shared) -> None:
        super().__init__(shared.state_coord)
        self._attr_unique_id = f"{shared.unique_id_prefix}-binary_sensor-errors"
        self._attr_device_info = shared.device_info

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.errors)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {"codes": list(self.coordinator.data.errors)}


class Door(ZoneEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key=zones.DOOR_KEY)
        self._attr_translation_key, name = zone_translation("door", zone)
        if name:
            self._attr_name = name

    @property
    def is_on(self) -> bool | None:
        closed = (self.zone_data or {}).get(zones.DOOR_KEY)
        return None if closed is None else not closed
