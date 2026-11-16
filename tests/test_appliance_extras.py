"""Hob, wine cabinet, washer (OptiDos), dishwasher options and eco extras."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.vzug import zones
from custom_components.vzug.api import VZugApi
from custom_components.vzug.binary_sensor import PanDetected, ProgramFlag
from custom_components.vzug.number import Illumination
from custom_components.vzug.select import TemperatureUnit
from custom_components.vzug.sensor import HobLevel, ProgramValue
from custom_components.vzug.sensor import _zone_entities as sensor_entities

HOB = [
    {
        "id": 1501,
        "status": "active",
        "zone": "1",
        "level": {"set": 7.5, "act": 7.5},
        "xc": 30,
        "yc": 40,
        "radius": 9,
    },
    {"id": 0, "status": "idle", "zone": "2", "level": {"set": 0}},
]


def _shared(raw, modes=None):
    coord = MagicMock(async_request_refresh=AsyncMock(), last_update_success=True)
    coord.data = zones.ZoneState(zones=zones.index_zones(raw), modes=modes or {})
    return SimpleNamespace(
        zone_coord=coord,
        client=MagicMock(set_cmd_value=AsyncMock()),
        unique_id_prefix="fc:1b:ff:00:00:02",
        device_info={},
    )


def test_hob_zones_are_read_only_readings():
    shared = _shared(HOB)
    levels = [e for e in sensor_entities(shared) if isinstance(e, HobLevel)]
    assert [(e.vzug_zone, e.native_value) for e in levels] == [("1", 7.5), ("2", 0)]
    assert levels[1]._attr_translation_placeholders == {"zone": "B"}
    assert PanDetected(shared, zone="1").is_on is True
    assert PanDetected(shared, zone="2").is_on is False


@pytest.mark.asyncio
async def test_wine_cabinet_light_and_unit():
    shared = _shared(
        [{"id": 2000, "zone": "fridge1"}],
        {"Illumination": "3", "TemperatureUnit": "°C"},
    )
    light = Illumination(shared)
    assert light.native_value == 3
    await light.async_set_native_value(5)
    shared.client.set_cmd_value.assert_awaited_with("Illumination", "5")

    unit = TemperatureUnit(shared)
    assert unit.current_option == "°C"
    await unit.async_select_option("°F")
    shared.client.set_cmd_value.assert_awaited_with("TemperatureUnit", "°F")


def test_dishwasher_options_and_washer_levels():
    coord = MagicMock()
    coord.data = zones.ProgramState(
        names={},
        current={
            "id": 50,
            "energySaving": {"set": True, "options": [True, False]},
            "fillLevelA": {"act": "reserve"},
        },
    )
    shared = SimpleNamespace(program_coord=coord, unique_id_prefix="x", device_info={})
    assert ProgramFlag(shared, key="energySaving").is_on is True
    assert ProgramFlag(shared, key="dryPlus").is_on is None
    assert ProgramValue(shared, key="fillLevelA").native_value == "reserve"


@pytest.mark.asyncio
async def test_optidos_before_hh_1_12_uses_get_command():
    api = VZugApi(base_url="http://example.com")
    api.hh_api_version = (1, 7, 0)
    answers = {
        "detergentAneutral": {"value": "Colour detergent"},
        "dosageA": {"value": "70", "minMax": ["100", "40"]},
    }

    async def command(component, *, command, params=None, **kwargs):
        return answers.get(params["value"], {})

    with patch.object(api, "_command", side_effect=command):
        optidos = await api.get_optidos()
    assert optidos["detergentAneutral"]["value"] == "Colour detergent"
    assert optidos["detergentAneutral"]["type"] == "selection"
    assert optidos["dosageA"]["minMax"] == ("40", "100")
    assert "dosageB" not in optidos


@pytest.mark.asyncio
async def test_optidos_from_user_settings():
    api = VZugApi(base_url="http://example.com")
    api.hh_api_version = (1, 12, 0)
    answers = {
        '{"id":"DETERGENT_A"}': {"value": {"set": "WOOL"}},
        '{"id":"DOSAGE_A"}': {"value": {"set": 60, "min": 20, "max": 120}},
    }

    async def command(component, *, command, params=None, **kwargs):
        assert command == "getUserSettings"
        return answers.get(params["value"], {})

    with patch.object(api, "_command", side_effect=command):
        optidos = await api.get_optidos()
    assert optidos["detergentAneutral"]["value"] == "Woollens detergent"
    assert optidos["dosageA"]["value"] == "60"
    assert optidos["dosageA"]["minMax"] == ("20", "120")


@pytest.mark.asyncio
async def test_eco_info_of_a_fridge_is_not_empty():
    api = VZugApi(base_url="http://example.com")
    fridge = {"doorOpenings": [{"today": {"duration": 12, "amount": 3}}]}
    with patch.object(api, "_command", AsyncMock(return_value=fridge)):
        assert await api.get_eco_info() == fridge
