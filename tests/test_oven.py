"""Oven / steamer zones, based on a CombairSteamer V6000 (hh API 1.11.0)."""

import json
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.vzug import zones
from custom_components.vzug.binary_sensor import OvenDoor, ProbeInserted, TimerRinging
from custom_components.vzug.button import StartWarmingDrawer, StopZone
from custom_components.vzug.number import Timer, WarmingDrawerDuration
from custom_components.vzug.number import _zone_entities as number_entities
from custom_components.vzug.sensor import OvenValue
from custom_components.vzug.sensor import _zone_entities as sensor_entities
from custom_components.vzug.switch import Light
from custom_components.vzug.switch import _zone_entities as switch_entities

STEAMER = json.loads(
    (
        pathlib.Path(__file__).parent
        / "fixtures/combair_steamer_v6000_76c/responses/hh_get_getprogram.json"
    ).read_text()
)


def _shared(raw=STEAMER):
    coord = MagicMock(async_request_refresh=AsyncMock(), last_update_success=True)
    coord.data = zones.ZoneState(zones=zones.index_zones(raw), modes={})
    client = MagicMock(
        set_program_dto=AsyncMock(),
        stop_program=AsyncMock(),
        set_zone_value=AsyncMock(),
        hh_supports=lambda version: True,
    )
    return SimpleNamespace(
        zone_coord=coord,
        client=client,
        unique_id_prefix="fc:1b:ff:00:00:01",
        device_info={},
        boost_hours={},
        warming_drawer_minutes={},
    )


def test_oven_entities():
    shared = _shared()
    values = [e for e in sensor_entities(shared) if isinstance(e, OvenValue)]
    assert {e._attr_translation_key for e in values} == set(OvenValue.VALUES.values())
    door = [e for e in values if e.vzug_key == "doorStatus"][0]
    assert door.native_value == "closed"
    # no program, no temperature
    assert [e for e in values if e.vzug_key == "temp"][0].native_value is None

    assert OvenDoor(shared, zone="cookingChamber1").is_on is False
    assert ProbeInserted(shared, zone="cookingChamber1").is_on is False
    assert TimerRinging(shared, zone="countdown1").is_on is False

    numbers = number_entities(shared)
    # the oven's temperature isn't a number to change, the drawer's duration is
    assert [type(e).__name__ for e in numbers] == ["Timer", "WarmingDrawerDuration"]


@pytest.mark.asyncio
async def test_oven_light_sends_booleans():
    shared = _shared()
    [light] = [e for e in switch_entities(shared) if isinstance(e, Light)]
    assert light.is_on is False
    await light.async_turn_on()
    shared.client.set_program_dto.assert_awaited_once_with(
        {"zone": "cookingChamber1", "light": True}
    )


@pytest.mark.asyncio
async def test_oven_timer_starts_like_the_app():
    shared = _shared()
    timer = Timer(shared, zone="countdown1")
    await timer.async_set_native_value(10)
    shared.client.set_program_dto.assert_awaited_once_with(
        {"zone": "countdown1", "id": 9000, "status": "active", "duration": 600}
    )
    await timer.async_set_native_value(0)
    shared.client.stop_program.assert_awaited_once_with("countdown1")
    shared.client.set_zone_value.assert_not_called()


@pytest.mark.asyncio
async def test_warming_drawer():
    shared = _shared()
    duration = WarmingDrawerDuration(shared, zone="warmingDrawer1")
    assert duration.native_value == 120
    assert (duration.native_min_value, duration.native_max_value) == (30, 720)
    duration.async_write_ha_state = MagicMock()
    await duration.async_set_native_value(90)

    await StartWarmingDrawer(shared, zone="warmingDrawer1").async_press()
    shared.client.set_program_dto.assert_awaited_once_with(
        {"id": 103, "zone": "warmingDrawer1", "duration": 5400, "status": "selected"}
    )
    await StopZone(shared, zone="warmingDrawer1").async_press()
    shared.client.stop_program.assert_awaited_once_with("warmingDrawer1")


def test_running_oven_values():
    raw = [
        {
            "id": 4,
            "status": "active",
            "zone": "cookingChamber1",
            "temp": {"set": 180, "act": 143, "min": 30, "max": 250},
            "doorStatus": {"act": "locked"},
        }
    ]
    shared = _shared(raw)
    temp = OvenValue(shared, zone="cookingChamber1", key="temp", field="act")
    assert temp.native_value == 143
    assert OvenDoor(shared, zone="cookingChamber1").is_on is False
