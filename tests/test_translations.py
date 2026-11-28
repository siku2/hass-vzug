"""The translation and icon files fit together and fit the entities."""

import json
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .appliance import DEVICES, ApplianceNetwork
from .common import setup_appliance

COMPONENT = Path(__file__).parent.parent / "custom_components" / "vzug"
LANGUAGES = sorted(p.stem for p in (COMPONENT / "translations").glob("*.json"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _keys(data: dict, prefix: str = "") -> set[str]:
    keys = set()
    for key, value in data.items():
        if isinstance(value, dict):
            keys |= _keys(value, f"{prefix}{key}.")
        else:
            keys.add(f"{prefix}{key}")
    return keys


def test_every_icon_has_a_translated_entity() -> None:
    english = _load(COMPONENT / "translations" / "en.json")["entity"]
    icons = _load(COMPONENT / "icons.json")["entity"]
    for platform, entities in icons.items():
        for key in entities:
            assert key in english.get(platform, {}), f"{platform}.{key}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_languages_have_no_unknown_keys(language: str) -> None:
    english = _keys(_load(COMPONENT / "translations" / "en.json"))
    other = _keys(_load(COMPONENT / "translations" / f"{language}.json"))
    assert other - english == set()


@pytest.mark.parametrize("language", LANGUAGES)
def test_exceptions_and_flow_are_translated(language: str) -> None:
    english = _load(COMPONENT / "translations" / "en.json")
    other = _load(COMPONENT / "translations" / f"{language}.json")
    for section in ("config", "exceptions", "issues"):
        assert _keys(other[section]) == _keys(english[section]), section


@pytest.mark.parametrize("device", DEVICES)
async def test_every_entity_is_translated(
    hass: HomeAssistant, appliances: ApplianceNetwork, device: str
) -> None:
    english = _load(COMPONENT / "translations" / "en.json")["entity"]
    entry = await setup_appliance(hass, appliances.add(device))
    for entity in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if entity.translation_key is not None:
            assert "name" in english[entity.domain][entity.translation_key], (
                entity.entity_id
            )
        else:
            # only the settings the appliance names itself, and unknown zones
            assert entity.original_name, entity.entity_id
