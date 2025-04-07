from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .helpers import UserConfigEntity
from .shared import Shared


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared: Shared = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SwitchEntity] = []

    for category in shared.config_coord.data.values():
        for command in category.commands.values():
            if command.get("type") == "boolean" and command.get("alterable", True):
                entities.append(
                    UserConfig(
                        shared,
                        category_key=category.key,
                        command_key=command.get("command", ""),
                    )
                )

    async_add_entities(entities)


class UserConfig(SwitchEntity, UserConfigEntity):
    @property
    def is_on(self) -> bool | None:
        value = self.vzug_command.get("value")
        match value:
            case "true":
                return True
            case "false":
                return False
            case _:
                return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._vzug_set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._vzug_set_state(False)

    async def _vzug_set_state(self, on: bool) -> None:
        await self.shared.client.set_command(
            self.vzug_command_key, "true" if on else "false"
        )
        await self.coordinator.async_request_refresh()
