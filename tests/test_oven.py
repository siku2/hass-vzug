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


def _program_shared(current):
    coord = MagicMock(async_request_refresh=AsyncMock(), async_refresh=AsyncMock())
    coord.data = zones.ProgramState(names={4: "hot_air"}, current=current)
    return SimpleNamespace(
        program_coord=coord,
        client=MagicMock(set_program=AsyncMock()),
        unique_id_prefix="x",
        device_info={},
        program_zone="cookingChamber1",
        program_settings={},
        start_delay_hours=0.0,
    )


@pytest.mark.asyncio
async def test_oven_program_is_selected_in_the_cooking_chamber():
    from custom_components.vzug.select import ProgramSelect

    shared = _program_shared(None)
    await ProgramSelect(shared).async_select_option("hot_air")
    shared.client.set_program.assert_awaited_once_with(4, {"zone": "cookingChamber1"})


@pytest.mark.asyncio
async def test_send_oven_program_with_temperature_and_duration():
    from custom_components.vzug.button import SendProgram
    from custom_components.vzug.number import ProgramSetting

    selected = {
        "id": 4,
        "status": "selected",
        "zone": "cookingChamber1",
        "temp": {"set": 180, "min": 30, "max": 250, "step": 5},
        "duration": {"set": 3600, "min": 60, "max": 86340, "step": 60},
        "preheat": {"set": False, "options": [True, False]},
    }
    shared = _program_shared(selected)
    temp = ProgramSetting(shared, key="temp")
    duration = ProgramSetting(shared, key="duration")
    assert (temp.native_value, duration.native_value) == (180, 60)
    for entity in (temp, duration):
        entity.async_write_ha_state = MagicMock()
    await temp.async_set_native_value(200)
    await duration.async_set_native_value(45)
    # out of range, so the oven keeps its own value
    shared.program_settings["temp"] = 400

    await SendProgram(shared).async_press()
    shared.client.set_program.assert_awaited_once_with(
        4, {"preheat": False, "zone": "cookingChamber1", "duration": 2700}
    )


@pytest.mark.asyncio
async def test_no_new_oven_program_while_one_runs():
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.vzug.button import SendProgram

    shared = _program_shared({"id": 4, "status": "active", "zone": "cookingChamber1"})
    with pytest.raises(HomeAssistantError):
        await SendProgram(shared).async_press()
    shared.client.set_program.assert_not_called()


@pytest.mark.asyncio
async def test_remote_start_is_opt_in_and_reports_a_refusal():
    import httpx
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.vzug.button import StartProgram

    shared = _program_shared({"id": 4, "status": "selected", "zone": "cookingChamber1"})
    shared.client.set_program_dto = AsyncMock()
    button = StartProgram(shared)
    assert button.entity_registry_enabled_default is False
    await button.async_press()
    shared.client.set_program_dto.assert_awaited_once_with(
        {"status": "active", "zone": "cookingChamber1"}
    )

    response = httpx.Response(
        400, text="400.04", request=httpx.Request("GET", "http://x")
    )
    shared.client.set_program_dto = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "", request=response.request, response=response
        )
    )
    with pytest.raises(HomeAssistantError) as err:
        await button.async_press()
    assert err.value.translation_placeholders == {"status": "400", "response": "400.04"}
