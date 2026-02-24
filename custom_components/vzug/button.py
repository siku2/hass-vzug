from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import Shared
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

    entities: list[ButtonEntity] = []
    if shared.meta.supports_update_status():
        entities.append(CheckUpdate(shared))

    for category in shared.config_coord.data.values():
        for command in category.commands.values():
            if command.get("type") == "action":
                entities.append(
                    UserConfig(
                        shared,
                        category_key=category.key,
                        command_key=command.get("command", ""),
                    )
                )

    async_add_entities(entities)


class CheckUpdate(ButtonEntity):
    _attr_device_class = ButtonDeviceClass.UPDATE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_translation_key = "check_update"

    def __init__(self, shared: Shared) -> None:
        self.shared = shared

        self._attr_unique_id = f"{shared.unique_id_prefix}-check-update"
        self._attr_device_info = shared.device_info

    async def async_press(self) -> None:
        try:
            await self.shared.client.check_for_updates()
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="check_update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.shared.update_coord.async_request_refresh()


class UserConfig(ButtonEntity, UserConfigEntity):
    async def async_press(self) -> None:
        try:
            await self.shared.client.do_command_action(self.vzug_command_key)
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_action_failed",
                translation_placeholders={
                    "command_key": self.vzug_command_key,
                    "error": str(err),
                },
            ) from err
