from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
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
        try:
            await self.shared.client.set_command(
                self.vzug_command_key, "true" if on else "false"
            )
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
