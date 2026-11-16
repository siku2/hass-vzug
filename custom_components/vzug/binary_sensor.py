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
from .helpers import ZoneEntity, snake, zone_translation
from .shared import ProgramCoordinator, Shared, StateCoordinator


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
        zone_map = shared.zone_coord.data.zones
        entities.extend(
            Door(shared, zone=name)
            for name, zone in zone_map.items()
            if isinstance(zone.get(zones.DOOR_KEY), bool)
        )
        for name, zone in zone_map.items():
            if zones.is_oven_zone(name, zone):
                entities.append(OvenDoor(shared, zone=name))
                entities.append(ProbeInserted(shared, zone=name))
            if zones.is_timer_zone(name):
                entities.append(TimerRinging(shared, zone=name))
            if zones.is_hob_zone(name):
                entities.append(PanDetected(shared, zone=name))
    if shared.program_coord is not None:
        entities.extend(
            ProgramFlag(shared, key=key)
            for key in zones.PROGRAM_FLAGS.get(shared.meta.machine_type, ())
        )
    async_add_entities(entities)


class OvenDoor(ZoneEntity, BinarySensorEntity):
    """The oven reports 'doorStatus' as 'open', 'closed' or 'locked'."""

    _attr_device_class = BinarySensorDeviceClass.DOOR
    _attr_translation_key = "oven_door"

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key="doorStatus")

    @property
    def is_on(self) -> bool | None:
        status = zones.value_field(self.zone_data, self.vzug_key, "act")
        return None if status is None else status == "open"


class ProbeInserted(ZoneEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PLUG
    _attr_translation_key = "probe_inserted"
    _attr_icon = "mdi:thermometer-probe"

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key="probeInserted")

    @property
    def is_on(self) -> bool | None:
        return zones.flag(self.zone_data, self.vzug_key)


class TimerRinging(ZoneEntity, BinarySensorEntity):
    """The kitchen timer ran out and rings until someone stops it."""

    _attr_translation_key = "timer_ringing"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key="ringing")

    @property
    def is_on(self) -> bool:
        zone = self.zone_data or {}
        left = zones.value_field(zone, zones.TIMER_KEY, "act")
        return zone.get("status") == "idle" and left == 0


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


class PanDetected(ZoneEntity, BinarySensorEntity):
    """A pan stands on this hob zone. Its position and size are attributes."""

    _attr_translation_key = "pan_detected"
    _attr_icon = "mdi:pot-steam-outline"

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key="pan")
        self._attr_translation_placeholders = {"zone": zones.hob_zone_letter(zone)}

    @property
    def is_on(self) -> bool | None:
        return zones.pan_detected(self.zone_data)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        zone = self.zone_data or {}
        return {
            key: zones.value(zone, key)
            for key in ("xc", "yc", "radius", "width", "height")
        }


class ProgramFlag(CoordinatorEntity[ProgramCoordinator], BinarySensorEntity):
    """An option of the selected program, ex. a dishwasher's EnergySaving."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, shared: Shared, *, key: str) -> None:
        super().__init__(shared.program_coord)
        self.vzug_key = key
        self._attr_unique_id = f"{shared.unique_id_prefix}-program-flag-{key}"
        self._attr_device_info = shared.device_info
        self._attr_translation_key = snake(key)

    @property
    def is_on(self) -> bool | None:
        current = self.coordinator.data.current if self.coordinator.data else None
        return zones.flag(current, self.vzug_key)
