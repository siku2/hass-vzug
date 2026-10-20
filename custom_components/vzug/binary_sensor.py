from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import zones
from .const import DOMAIN
from .helpers import ZoneEntity, zone_translation
from .shared import Shared


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared: Shared = hass.data[DOMAIN][config_entry.entry_id]
    if shared.zone_coord is None:
        return

    async_add_entities(
        Door(shared, zone=name)
        for name, zone in shared.zone_coord.data.zones.items()
        if isinstance(zone.get(zones.DOOR_KEY), bool)
    )


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
