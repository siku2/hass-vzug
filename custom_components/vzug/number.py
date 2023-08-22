from homeassistant.components.number import NumberEntity, NumberMode
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

    entities: list[NumberEntity] = []

    for category in shared.config_coord.data.values():
        for command in category.commands.values():
            if command.get("type") == "range" and command.get("alterable", False):
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
        await self.shared.client.set_command(self.vzug_command_key, str(int(value)))
        await self.coordinator.async_request_refresh()
