from homeassistant.const import EntityCategory
from homeassistant.helpers.typing import UndefinedType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import api
from .coordinator import ConfigCoordinator, Shared

# Map known German command descriptions to English names.
# The device API returns descriptions in the device's configured language.
# This provides English defaults for known commands across V-ZUG appliances.
_KNOWN_ENGLISH_NAMES: dict[str, str] = {
    # Common across devices
    "Helligkeit": "Brightness",
    "Helligkeit ": "Brightness",
    "Tastenton": "Key Tone",
    "Signalton": "Signal Tone",
    "Kindersicherung": "Child Lock",
    "Temperatureinheit": "Temperature Unit",
    "Hintergrundbild": "Background Image",
    # Dishwasher
    "Startaufschub [h]": "Start Delay [h]",
    "Startaufschub Uhrzeit": "Start Delay Time",
    "Wasserhärteeinheit": "Water Hardness Unit",
    "Glanzmittel": "Rinse Aid",
    "Wasserhärte": "Water Hardness",
    "Energiesparen": "Energy Saving",
    "Teilbeladung": "Partial Load",
    "TrocknenPlus": "Dry Plus",
    "SpülenPlus": "Rinse Plus",
    # Washing machine
    "Schleudern": "Spin",
    "Verschmutzung": "Soil Level",
    "Türöffnungsautomatik": "Auto Door Open",
    "Hygieneinfo": "Hygiene Info",
    "Trommelbeleuchtung": "Drum Light",
    # Dryer
    "Trockengrad": "Drying Level",
    "Blickwinkel": "Viewing Angle",
    "ReversierenPlus": "Reverse Plus",
    "EcoManagement": "Eco Management",
    "Durchschnitt pro Charge": "Average per Cycle",
    "Gesamtverbrauch": "Total Consumption",
}


class UserConfigEntity(CoordinatorEntity[ConfigCoordinator]):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, shared: Shared, *, category_key: str, command_key: str) -> None:
        super().__init__(shared.config_coord)
        self.shared = shared
        self.vzug_category_key = category_key
        self.vzug_command_key = command_key

        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-userconfig-{category_key}-{command_key}"
        )
        self._attr_device_info = shared.device_info
        self._attr_extra_state_attributes = {
            "category_key": category_key,
            "command_key": command_key,
        }

    @property
    def vzug_command(self) -> api.Command:
        try:
            return self.coordinator.data[self.vzug_category_key].commands[
                self.vzug_command_key
            ]
        except LookupError:
            return api.Command()

    @property
    def name(self) -> str | UndefinedType | None:
        description = self.vzug_command.get("description")
        if not description:
            return self.vzug_command_key
        return _KNOWN_ENGLISH_NAMES.get(description, description)

    @property
    def entity_category(self) -> EntityCategory | None:
        return (
            EntityCategory.CONFIG
            if self.vzug_command.get("alterable", False)
            else EntityCategory.DIAGNOSTIC
        )
