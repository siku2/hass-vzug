from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Shared, StateCoordinator
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

    if shared.program_list:
        entities.append(ProgramSelect(shared))

    async_add_entities(entities)


class UserConfig(SelectEntity, UserConfigEntity):
    @property
    def current_option(self) -> str | None:
        return self.vzug_command.get("value")

    @property
    def options(self) -> list[str]:
        return self.vzug_command.get("options", [])

    async def async_select_option(self, option: str) -> None:
        try:
            await self.shared.client.set_command(self.vzug_command_key, option)
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


class ProgramSelect(SelectEntity, CoordinatorEntity[StateCoordinator]):
    _attr_has_entity_name = True
    _attr_translation_key = "program_select"

    def __init__(self, shared: Shared) -> None:
        super().__init__(shared.state_coord)
        self.shared = shared

        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-select-{self.translation_key}"
        )
        self._attr_device_info = shared.device_info

        # Build name→id mapping
        self._name_to_id: dict[str, int] = {
            name: pid for pid, name in shared.program_list.items()
        }

    @property
    def options(self) -> list[str]:
        return list(self.shared.program_list.values())

    @property
    def current_option(self) -> str | None:
        current_program = self.coordinator.data.device.get("Program")
        if not current_program:
            return None
        # Try to match by name directly
        if current_program in self._name_to_id:
            return current_program
        # Try to resolve numeric program ID to name
        try:
            pid = int(current_program)
            name = self.shared.program_list.get(pid)
            if name and name in self._name_to_id:
                return name
        except (ValueError, TypeError):
            pass
        return None

    async def async_select_option(self, option: str) -> None:
        program_id = self._name_to_id.get(option)
        if program_id is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_command_failed",
                translation_placeholders={
                    "command_key": "program",
                    "error": f"Unknown program: {option}",
                },
            )
        try:
            await self.shared.client.set_program(program_id)
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_command_failed",
                translation_placeholders={
                    "command_key": "program",
                    "error": str(err),
                },
            ) from err
        await self.coordinator.async_request_refresh()
