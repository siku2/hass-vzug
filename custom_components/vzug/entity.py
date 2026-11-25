"""Base entities of the V-ZUG integration."""

from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import UndefinedType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import api, zones
from .coordinator import ConfigCoordinator, Shared, ZoneCoordinator
from .helpers import name_from_command_key


class VZugBaseEntity(Entity):
    """An entity of one appliance, named after its device.

    'unique_id_suffix' is appended to the appliance's MAC address. It must never
    change: the entity registry finds the entity by it.
    """

    _attr_has_entity_name = True

    def __init__(self, shared: Shared, *, unique_id_suffix: str) -> None:
        self.shared = shared
        self._attr_unique_id = f"{shared.unique_id_prefix}-{unique_id_suffix}"
        self._attr_device_info = shared.device_info


class VZugEntity[CoordinatorT: DataUpdateCoordinator[Any]](
    CoordinatorEntity[CoordinatorT], VZugBaseEntity
):
    """An entity showing the data of one of the appliance's coordinators."""

    def __init__(
        self, shared: Shared, coordinator: CoordinatorT, *, unique_id_suffix: str
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        VZugBaseEntity.__init__(self, shared, unique_id_suffix=unique_id_suffix)


class UserConfigEntity(VZugEntity[ConfigCoordinator]):
    """A setting from the appliance's category tree ('getCategories')."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, shared: Shared, *, category_key: str, command_key: str) -> None:
        super().__init__(
            shared,
            shared.config_coord,
            unique_id_suffix=f"userconfig-{category_key}-{command_key}",
        )
        self.vzug_category_key = category_key
        self.vzug_command_key = command_key
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
            name = name_from_command_key(self.vzug_command_key)
        return name

    @property
    def entity_category(self) -> EntityCategory | None:
        return (
            EntityCategory.CONFIG
            if self.vzug_command.get("alterable", False)
            else EntityCategory.DIAGNOSTIC
        )


class ZoneEntity(VZugEntity[ZoneCoordinator]):
    """An entity reading one key of one zone of a refrigerator.

    'zone' is the appliance's zone name ('fridge1', 'freezer1', 'countdown1'), or ""
    for entities about the whole appliance (PartyCooling, the 'cmd' modes).
    """

    def __init__(self, shared: Shared, *, zone: str, key: str) -> None:
        assert shared.zone_coord is not None
        super().__init__(
            shared,
            shared.zone_coord,
            unique_id_suffix=f"zone-{zone or 'all'}-{key}",
        )
        self.vzug_zone = zone
        self.vzug_key = key

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
