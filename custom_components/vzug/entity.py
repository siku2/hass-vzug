"""Base entities of the V-ZUG integration."""

import functools
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Concatenate

import httpx
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import UndefinedType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import api, zones
from .const import DOMAIN
from .coordinator import ConfigCoordinator, Shared, ZoneCoordinator
from .helpers import name_from_command_key


def vzug_action[EntityT: "VZugBaseEntity", **P, R](
    func: Callable[Concatenate[EntityT, P], Awaitable[R]],
) -> Callable[Concatenate[EntityT, P], Coroutine[Any, Any, R]]:
    """Turn a failed request to the appliance into an error the user sees.

    Without this an action (pressing a button, switching a switch) that fails
    shows up as an unexpected exception with a traceback in the log instead of
    as a message in the frontend.
    """

    @functools.wraps(func)
    async def wrapper(self: EntityT, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(self, *args, **kwargs)
        except HomeAssistantError:
            raise
        except api.AuthenticationFailed as err:
            self.shared.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except httpx.HTTPStatusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="request_refused",
                translation_placeholders={
                    "status": str(err.response.status_code),
                    "response": err.response.text.strip(),
                },
            ) from err
        except (httpx.HTTPError, ValueError, AssertionError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": repr(err)},
            ) from err

    return wrapper


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


def user_config_entities[EntityT: UserConfigEntity](
    shared: Shared,
    async_add_entities: AddConfigEntryEntitiesCallback,
    wanted: Callable[[api.Command], bool],
    factory: Callable[..., EntityT],
) -> list[EntityT]:
    """Entities for the settings in the category tree that 'wanted' picks.

    Returns those the appliance has now, and adds the ones that show up later
    (ex. after a firmware update, or once a busy appliance lists them all).
    """
    known: set[tuple[str, str]] = set()

    def collect() -> list[EntityT]:
        new: list[EntityT] = []
        for category in (shared.config_coord.data or {}).values():
            for command in category.commands.values():
                key = (category.key, command.get("command", ""))
                if key in known or not wanted(command):
                    continue
                known.add(key)
                new.append(factory(shared, category_key=key[0], command_key=key[1]))
        return new

    @callback
    def add_new() -> None:
        if new := collect():
            async_add_entities(new)

    shared.config_entry.async_on_unload(shared.config_coord.async_add_listener(add_new))
    return collect()


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
