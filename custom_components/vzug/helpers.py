"""Naming helpers shared by the platforms."""

import re

_KEY_SEPARATOR = re.compile(r"(?<=[a-z0-9])X(?=[A-Za-z0-9])|_+")


def name_from_command_key(command_key: str) -> str:
    """A readable name for a command the appliance doesn't describe.

    The keys use an 'X' or '_' between words: 'ecomXstatXtotalXclear' becomes
    'Ecom stat total clear', 'AUTO_DOOR_OPENER' becomes 'Auto door opener'.
    """
    words = [word for word in _KEY_SEPARATOR.split(command_key) if word]
    if not words:
        return command_key
    name = " ".join(words)
    if name.isupper():
        name = name.lower()
    return name[0].upper() + name[1:]


def zone_label(zone: str) -> str:
    """'fridge1' -> 'fridge', used as translation placeholder"""
    return zone.rstrip("0123456789")


# translation keys must be snake_case
_SNAKE = {
    "superCool": "super_cool",
    "superFreeze": "super_freeze",
    "partyCooling": "party_cooling",
    "HolidayMode": "holiday_mode",
    "SilentPlusMode": "silent_plus_mode",
    "SabbatMode": "sabbath_mode",
    "MonoFridgeMode": "mono_fridge_mode",
    "TemperatureUnit": "temperature_unit",
}
# zones we have translations for, anything else gets a generated name
KNOWN_ZONE_LABELS = ("fridge", "freezer")


def zone_translation(prefix: str, zone: str) -> tuple[str | None, str | None]:
    """(translation_key, fallback name) for an entity about one zone."""
    label = zone_label(zone)
    if label in KNOWN_ZONE_LABELS:
        return f"{prefix}_{label}", None
    return None, f"{prefix.replace('_', ' ').capitalize()} {zone}"


def snake(key: str) -> str:
    return _SNAKE.get(key, key.lower())
