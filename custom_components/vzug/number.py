from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import UserConfigEntity

if TYPE_CHECKING:
    from . import VZugConfigEntry

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VZugConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared = config_entry.runtime_data

    entities: list[NumberEntity] = []

    for category in shared.config_coord.data.values():
        for command in category.commands.values():
            if command.get("type") == "range" and command.get("alterable", True):
                entities.append(
                    UserConfig(
                        shared,
                        category_key=category.key,
                        command_key=command.get("command", ""),
                    )
                )

    async_add_entities(entities)


class UserConfig(NumberEntity, UserConfigEntity):
    _attr_mode = NumberMode.SLIDER

    @property
    def native_min_value(self) -> float:
        try:
            return float(self.vzug_command["minMax"][0])
        except (ValueError, LookupError, TypeError):
            return 0.0

    @property
    def native_max_value(self) -> float:
        try:
            return float(self.vzug_command["minMax"][1])
        except (ValueError, LookupError, TypeError):
            return 0.0

    @property
    def native_step(self) -> float | None:
        return 1.0

    @property
    def native_value(self) -> float | None:
        value = self.vzug_command.get("value")
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.shared.client.set_command(self.vzug_command_key, str(int(value)))
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_command_failed",
                translation_placeholders={
                    "command_key": self.vzug_command_key,
                    "error": str(err),
                },
            ) from err
        await self.coordinator.async_request_refresh()
