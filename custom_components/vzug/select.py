from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import zones
from .entity import UserConfigEntity, vzug_action, VZugEntity, ZoneEntity
from .coordinator import ProgramCoordinator, Shared, VZugConfigEntry


# the appliance handles one request at a time, so do the actions
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

    if shared.program_coord is not None:
        entities.append(ProgramSelect(shared))
    if (
        shared.zone_coord is not None
        and zones.UNIT_MODE in shared.zone_coord.data.modes
    ):
        entities.append(TemperatureUnit(shared))

    async_add_entities(entities)


class ProgramSelect(VZugEntity[ProgramCoordinator], SelectEntity):
    """Pick a program, like tapping it in the V-ZUG app.

    This only selects the program on the appliance, it doesn't start it.
    """

    _attr_translation_key = "program_select"

    def __init__(self, shared: Shared) -> None:
        assert shared.program_coord is not None
        super().__init__(
            shared, shared.program_coord, unique_id_suffix="program-select"
        )

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
        entry = zones.PROGRAMS.get(str(current.get("id")), {})
        descriptions = entry.get("description", {})
        language = self.hass.config.language.split("-")[0] if self.hass else "en"
        return {
            "status": current.get("status", "idle"),
            "duration_seconds": zones.value_field(current, "duration", "set"),
            "description": descriptions.get(language) or descriptions.get("en"),
        }

    @vzug_action
    async def async_select_option(self, option: str) -> None:
        program_id = zones.program_id_by_key(self.coordinator.data.names, option)
        if program_id is None:
            raise ServiceValidationError(f"Unknown program {option!r}")
        # ovens pick the program for their cooking chamber
        if zone := getattr(self.shared, "program_zone", None):
            await self.shared.client.set_program(program_id, {"zone": zone})
        else:
            await self.shared.client.set_program(program_id)
        await self.coordinator.async_request_refresh()


class TemperatureUnit(ZoneEntity, SelectEntity):
    """°C or °F on the appliance's display; Home Assistant follows it."""

    _attr_translation_key = "temperature_unit"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = ["°C", "°F"]
    _attr_icon = "mdi:thermometer"

    def __init__(self, shared: Shared) -> None:
        super().__init__(shared, zone="", key=zones.UNIT_MODE)

    @property
    def current_option(self) -> str | None:
        return zones.temperature_unit(self.coordinator.data.modes)

    @vzug_action
    async def async_select_option(self, option: str) -> None:
        await self.shared.client.set_cmd_value(self.vzug_key, option)
        await self.coordinator.async_request_refresh()


class UserConfig(SelectEntity, UserConfigEntity):
    @property
    def current_option(self) -> str | None:
        return self.vzug_command.get("value")

    @property
    def options(self) -> list[str]:
        return self.vzug_command.get("options", [])

    @vzug_action
    async def async_select_option(self, option: str) -> None:
        await self.shared.client.set_command(self.vzug_command_key, option)
        await self.coordinator.async_request_refresh()
