from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import zones
from .entity import VZugEntity, ZoneEntity
from .helpers import snake, zone_translation
from .coordinator import ProgramCoordinator, Shared, StateCoordinator, VZugConfigEntry


# read only, the coordinators do the polling
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VZugConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared = config_entry.runtime_data
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

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key="probeInserted")

    @property
    def is_on(self) -> bool | None:
        return zones.flag(self.zone_data, self.vzug_key)


class TimerRinging(ZoneEntity, BinarySensorEntity):
    """The kitchen timer ran out and rings until someone stops it."""

    _attr_translation_key = "timer_ringing"

    def __init__(self, shared: Shared, *, zone: str) -> None:
        super().__init__(shared, zone=zone, key="ringing")

    @property
    def is_on(self) -> bool:
        zone = self.zone_data or {}
        left = zones.value_field(zone, zones.TIMER_KEY, "act")
        return zone.get("status") == "idle" and left == 0


class Errors(VZugEntity[StateCoordinator], BinarySensorEntity):
    """On while the appliance shows an error, the codes are attributes."""

    _attr_translation_key = "errors"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, shared: Shared) -> None:
        super().__init__(
            shared, shared.state_coord, unique_id_suffix="binary_sensor-errors"
        )

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


class ProgramFlag(VZugEntity[ProgramCoordinator], BinarySensorEntity):
    """An option of the selected program, ex. a dishwasher's EnergySaving."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, shared: Shared, *, key: str) -> None:
        assert shared.program_coord is not None
        super().__init__(
            shared, shared.program_coord, unique_id_suffix=f"program-flag-{key}"
        )
        self.vzug_key = key
        self._attr_translation_key = snake(key)

    @property
    def is_on(self) -> bool | None:
        current = self.coordinator.data.current if self.coordinator.data else None
        return zones.flag(current, self.vzug_key)
