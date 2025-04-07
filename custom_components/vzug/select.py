from homeassistant.components.select import SelectEntity
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

    entities: list[SelectEntity] = []

    for category in shared.config_coord.data.values():
        for command in category.commands.values():
            if command.get("type") == "selection" and command.get("alterable", True):
                entities.append(
                    UserConfig(
                        shared,
                        category_key=category.key,
                        command_key=command.get("command", ""),
                    )
                )

    async_add_entities(entities)


class UserConfig(SelectEntity, UserConfigEntity):
    @property
    def current_option(self) -> str | None:
        return self.vzug_command.get("value")

    @property
    def options(self) -> list[str]:
        return self.vzug_command.get("options", [])

    async def async_select_option(self, option: str) -> None:
        await self.shared.client.set_command(self.vzug_command_key, option)
        await self.coordinator.async_request_refresh()
