import pytest

from custom_components.vzug.helpers import name_from_command_key


@pytest.mark.parametrize(
    ("command_key", "name"),
    [
        ("ecomXstatXtotalXclear", "Ecom stat total clear"),
        ("autoXdoorXopener", "Auto door opener"),
        ("ButtonXtone", "Button tone"),
        ("LevelXofXdryness", "Level of dryness"),
        ("AUTO_DOOR_OPENER", "Auto door opener"),
        ("Brightness", "Brightness"),
        ("language", "Language"),
        ("MAX", "Max"),
    ],
)
def test_name_from_command_key(command_key, name):
    assert name_from_command_key(command_key) == name
