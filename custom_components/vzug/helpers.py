from homeassistant.const import EntityCategory
from homeassistant.helpers.typing import UndefinedType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import api, zones
from .shared import ConfigCoordinator, Shared, ZoneCoordinator


class UserConfigEntity(CoordinatorEntity[ConfigCoordinator]):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, shared: Shared, *, category_key: str, command_key: str) -> None:
        super().__init__(shared.config_coord)
        self.shared = shared
        self.vzug_category_key = category_key
        self.vzug_command_key = command_key

        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-userconfig-{category_key}-{command_key}"
        )
        self._attr_device_info = shared.device_info
        self._attr_extra_state_attributes = {
            "category_key": category_key,
            "command_key": command_key,
        }

    @property
    def vzug_command(self) -> api.Command:
        try:
            return self.coordinator.data[self.vzug_category_key].commands[
                self.vzug_command_key
            ]
        except LookupError:
            return api.Command()

    @property
    def name(self) -> str | UndefinedType | None:
        name = self.vzug_command.get("description")
        if not name:
            name = self.vzug_command_key
        return name

    @property
    def entity_category(self) -> EntityCategory | None:
        return (
            EntityCategory.CONFIG
            if self.vzug_command.get("alterable", False)
            else EntityCategory.DIAGNOSTIC
        )


class ZoneEntity(CoordinatorEntity[ZoneCoordinator]):
    """An entity reading one key of one zone of a refrigerator.

    'zone' is the appliance's zone name ('fridge1', 'freezer1', 'countdown1'), or ""
    for entities about the whole appliance (PartyCooling, the 'cmd' modes).
    """

    _attr_has_entity_name = True

    def __init__(self, shared: Shared, *, zone: str, key: str) -> None:
        assert shared.zone_coord is not None
        super().__init__(shared.zone_coord)
        self.shared = shared
        self.vzug_zone = zone
        self.vzug_key = key

        self._attr_unique_id = f"{shared.unique_id_prefix}-zone-{zone or 'all'}-{key}"
        self._attr_device_info = shared.device_info

    @property
    def zone_data(self) -> zones.Zone | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.zones.get(self.vzug_zone)

    @property
    def available(self) -> bool:
        return super().available and (not self.vzug_zone or self.zone_data is not None)

    async def _write_zone(self, value: str) -> None:
        await self.shared.client.set_zone_value(self.vzug_zone, self.vzug_key, value)
        await self.coordinator.async_request_refresh()


def zone_label(zone: str) -> str:
    """'fridge1' -> 'fridge', used as translation placeholder"""
    return zone.rstrip("0123456789")


# translation keys must be snake_case
_SNAKE = {
    "superCool": "super_cool",
    "superFreeze": "super_freeze",
    "partyCooling": "party_cooling",
    "HolidayMode": "holiday_mode",
    "SilentPlusMode": "silent_plus_mode",
    "SabbatMode": "sabbath_mode",
}
# zones we have translations for, anything else gets a generated name
KNOWN_ZONE_LABELS = ("fridge", "freezer")


def zone_translation(prefix: str, zone: str) -> tuple[str | None, str | None]:
    """(translation_key, fallback name) for an entity about one zone."""
    label = zone_label(zone)
    if label in KNOWN_ZONE_LABELS:
        return f"{prefix}_{label}", None
    return None, f"{prefix.replace('_', ' ').capitalize()} {zone}"


def snake(key: str) -> str:
    return _SNAKE.get(key, key.lower())
