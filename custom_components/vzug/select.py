from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import zones
from .const import DOMAIN
from .helpers import UserConfigEntity
from .shared import ProgramCoordinator, Shared


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

    if shared.program_coord is not None:
        entities.append(ProgramSelect(shared))

    async_add_entities(entities)


class ProgramSelect(CoordinatorEntity[ProgramCoordinator], SelectEntity):
    """Pick a program, like tapping it in the V-ZUG app.

    This only selects the program on the appliance, it doesn't start it.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "program_select"

    def __init__(self, shared: Shared) -> None:
        assert shared.program_coord is not None
        super().__init__(shared.program_coord)
        self.shared = shared
        self._attr_unique_id = f"{shared.unique_id_prefix}-program-select"
        self._attr_device_info = shared.device_info

    @property
    def options(self) -> list[str]:
        return [
            zones.program_key(name) for name in self.coordinator.data.names.values()
        ]

    @property
    def current_option(self) -> str | None:
        current = self.coordinator.data.current
        if current is None:
            return None
        name = self.coordinator.data.names.get(current.get("id"))
        return zones.program_key(name) if name else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        current = self.coordinator.data.current or {}
        return {
            "status": current.get("status", "idle"),
            "duration_seconds": zones.value_field(current, "duration", "set"),
        }

    async def async_select_option(self, option: str) -> None:
        program_id = zones.program_id_by_key(self.coordinator.data.names, option)
        if program_id is None:
            raise ValueError(f"unknown program {option!r}")
        await self.shared.client.set_program(program_id)
        await self.coordinator.async_request_refresh()


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
