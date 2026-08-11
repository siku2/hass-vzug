from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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

    entities: list[ButtonEntity] = [RefreshNow(shared)]
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


class RefreshNow(ButtonEntity):
    """Bring every value up to date right now, waking the appliance if necessary.

    While the appliance is in standby the state updates only talk to the AI module
    so it can stay asleep, and the config tree is only read hourly. Both are a
    deliberate trade-off, and this is the way out of it: for someone who just
    changed a setting on the appliance's panel, or for an automation that knows
    better than the integration does - a smart plug reporting power draw, a door
    contact, a motion sensor in the laundry room.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_translation_key = "refresh_now"

    def __init__(self, shared: Shared) -> None:
        self.shared = shared

        self._attr_unique_id = f"{shared.unique_id_prefix}-refresh-now"
        self._attr_device_info = shared.device_info

    async def async_press(self) -> None:
        await self.shared.async_probe_device()


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
        await self.shared.client.check_for_updates()
        await self.shared.update_coord.async_request_refresh()


class UserConfig(ButtonEntity, UserConfigEntity):
    async def async_press(self) -> None:
        await self.shared.client.do_command_action(self.vzug_command_key)
