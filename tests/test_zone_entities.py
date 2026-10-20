"""The refrigerator entities and the zone coordinator, without a running Home Assistant."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from custom_components.vzug import zones
from custom_components.vzug.binary_sensor import Door
from custom_components.vzug.number import BoostDuration, Timer, ZoneTemperature
from custom_components.vzug.number import _zone_entities as number_entities
from custom_components.vzug.sensor import ModeSensor, TimeLeft
from custom_components.vzug.sensor import _zone_entities as sensor_entities
from custom_components.vzug.shared import Shared
from custom_components.vzug.switch import Mode, TimedFunction
from custom_components.vzug.switch import _zone_entities as switch_entities

from .test_zones import COMBI_COOLER

MODES = {
    "HolidayMode": "false",
    "SilentPlusMode": "true",
    "SabbatMode": "0",
    "TemperatureUnit": "°C",
}


def _shared(raw=COMBI_COOLER, modes=MODES):
    coord = MagicMock()
    coord.data = zones.ZoneState(zones=zones.index_zones(raw), modes=dict(modes))
    coord.async_request_refresh = AsyncMock()
    coord.last_update_success = True
    shared = SimpleNamespace(
        zone_coord=coord,
        client=MagicMock(set_zone_value=AsyncMock(), set_cmd_value=AsyncMock()),
        unique_id_prefix="fc:1b:ff:06:6e:8e",
        device_info={},
        boost_hours={},
    )
    return shared


def test_entities_created_for_a_combi_cooler():
    shared = _shared()
    numbers = number_entities(shared)
    switches = switch_entities(shared)
    sensors = sensor_entities(shared)

    assert [type(e).__name__ for e in numbers] == [
        "ZoneTemperature",
        "ZoneTemperature",
        "BoostDuration",
        "BoostDuration",
        "BoostDuration",
        "Timer",
    ]
    # PartyCooling covers both zones, so it gets one switch
    assert [e.vzug_key for e in switches] == [
        "superCool",
        "superFreeze",
        "partyCooling",
        "HolidayMode",
        "SilentPlusMode",
    ]
    assert [e.vzug_key for e in sensors] == [
        "superCool",
        "superFreeze",
        "partyCooling",
        "SabbatMode",
    ]
    unique_ids = [e.unique_id for e in (*numbers, *switches, *sensors)]
    assert len(unique_ids) == len(set(unique_ids))


def test_no_entities_without_zones():
    shared = SimpleNamespace(zone_coord=None)
    assert number_entities(shared) == []
    assert switch_entities(shared) == []
    assert sensor_entities(shared) == []


@pytest.mark.asyncio
async def test_temperature():
    shared = _shared()
    fridge = ZoneTemperature(shared, zone="fridge1")
    assert fridge.translation_key == "temperature_fridge"
    assert (fridge.native_value, fridge.native_min_value, fridge.native_max_value) == (
        6.0,
        3.0,
        8.0,
    )
    assert fridge.native_unit_of_measurement == "°C"

    await fridge.async_set_native_value(7.0)
    shared.client.set_zone_value.assert_awaited_once_with("fridge1", "temp", "7")
    shared.zone_coord.async_request_refresh.assert_awaited()


@pytest.mark.asyncio
async def test_timed_function_uses_the_configured_duration():
    shared = _shared()
    duration = BoostDuration(shared, zone="fridge1", key="superCool")
    assert duration.native_value == 12.0
    assert duration.native_max_value == 24.0

    duration.async_write_ha_state = MagicMock()
    await duration.async_set_native_value(3)

    switch = TimedFunction(shared, zone="fridge1", key="superCool")
    assert switch.is_on is False
    await switch.async_turn_on()
    shared.client.set_zone_value.assert_awaited_with("fridge1", "superCool", "10800")
    await switch.async_turn_off()
    shared.client.set_zone_value.assert_awaited_with("fridge1", "superCool", "0")


def test_running_function_and_time_left():
    shared = _shared()
    assert TimedFunction(shared, zone="freezer1", key="superFreeze").is_on is True
    # 3596 s left, rounded up
    assert TimeLeft(shared, zone="freezer1", key="superFreeze").native_value == 60
    assert TimeLeft(shared, zone="fridge1", key="superCool").native_value == 0


@pytest.mark.asyncio
async def test_timer_in_minutes():
    shared = _shared()
    timer = Timer(shared, zone="countdown1")
    assert timer.native_value == 10.0
    assert timer.native_max_value == 595.0
    await timer.async_set_native_value(5)
    shared.client.set_zone_value.assert_awaited_with("countdown1", "duration", "300")
    await timer.async_set_native_value(0)
    shared.client.set_zone_value.assert_awaited_with("countdown1", "duration", "0")


@pytest.mark.asyncio
async def test_modes():
    shared = _shared()
    holiday = Mode(shared, mode="HolidayMode")
    silent = Mode(shared, mode="SilentPlusMode")
    assert holiday.is_on is False
    assert silent.is_on is True
    await holiday.async_turn_on()
    shared.client.set_cmd_value.assert_awaited_with("HolidayMode", "true")
    assert ModeSensor(shared, mode="SabbatMode").native_value == "off"


def test_doors():
    shared = _shared()
    assert Door(shared, zone="fridge1").is_on is False
    assert Door(shared, zone="freezer1").is_on is True
    assert Door(shared, zone="freezer1").translation_key == "door_freezer"


def test_zone_disappearing_makes_entities_unavailable():
    shared = _shared()
    fridge = ZoneTemperature(shared, zone="fridge1")
    shared.zone_coord.data = zones.ZoneState(zones={}, modes={})
    assert fridge.available is False


@pytest.fixture
def bare_shared():
    instance = Shared.__new__(Shared)
    instance.hass = MagicMock()
    instance.client = MagicMock()
    instance.zone_coord = None
    instance._zone_modes = ()
    instance._zone_stale_count = 0
    return instance


@pytest.mark.asyncio
async def test_setup_zones_skips_appliances_without_zones(bare_shared):
    bare_shared.client.get_raw_programs = AsyncMock(return_value=[{"status": "idle"}])
    await bare_shared._setup_zones()
    assert bare_shared.zone_coord is None


@pytest.mark.asyncio
async def test_setup_zones_probes_the_modes(bare_shared, monkeypatch):
    bare_shared.client.get_raw_programs = AsyncMock(return_value=COMBI_COOLER)

    async def get_cmd_value(name, attempts=2):
        if name == "SabbatMode":
            request = httpx.Request("GET", "http://x")
            raise httpx.HTTPStatusError(
                "404", request=request, response=httpx.Response(404, request=request)
            )
        return MODES[name]

    bare_shared.client.get_cmd_value = get_cmd_value
    coordinator = MagicMock(async_config_entry_first_refresh=AsyncMock())
    monkeypatch.setattr(
        "custom_components.vzug.shared.DataUpdateCoordinator",
        MagicMock(return_value=coordinator),
    )
    await bare_shared._setup_zones()
    assert bare_shared.zone_coord is coordinator
    assert bare_shared._zone_modes == (
        "HolidayMode",
        "SilentPlusMode",
        "TemperatureUnit",
    )

    bare_shared.zone_coord.data = None
    state = await bare_shared._fetch_zones()
    assert list(state.zones) == ["fridge1", "freezer1", "countdown1"]
    assert state.modes == {
        "HolidayMode": "false",
        "SilentPlusMode": "true",
        "TemperatureUnit": "°C",
    }


@pytest.mark.asyncio
async def test_fetch_zones_keeps_previous_data_for_a_while(bare_shared):
    previous = zones.ZoneState(zones=zones.index_zones(COMBI_COOLER), modes={})
    bare_shared.zone_coord = MagicMock(data=previous)
    bare_shared.client.get_raw_programs = AsyncMock(side_effect=httpx.ReadTimeout("x"))
    for _ in range(3):
        assert await bare_shared._fetch_zones() is previous
    with pytest.raises(Exception):
        await bare_shared._fetch_zones()


# what an AdoraDish V4000 answers to 'getProgram {"id": <id>}'
DISHWASHER_NAMES = {
    50: "Eco",
    51: "Automatic",
    86: "Quick",
    54: "Intensive",
    57: "Glass",
    58: "Fondue/Raclette",
    59: "Hygiene",
    61: "Pre-rinsing",
}


@pytest.mark.asyncio
async def test_setup_programs_learns_the_names(bare_shared, monkeypatch):
    bare_shared.program_coord = None
    bare_shared._program_names = {}
    bare_shared.client.get_raw_programs = AsyncMock(return_value=[{"status": "idle"}])
    bare_shared.client.get_all_program_ids = AsyncMock(
        return_value=list(DISHWASHER_NAMES)
    )
    bare_shared.client.get_program_details = AsyncMock(
        side_effect=lambda pid: {"id": pid, "name": DISHWASHER_NAMES[pid]}
    )
    coordinator = MagicMock(async_config_entry_first_refresh=AsyncMock(), data=None)
    monkeypatch.setattr(
        "custom_components.vzug.shared.DataUpdateCoordinator",
        MagicMock(return_value=coordinator),
    )

    await bare_shared._setup_zones()

    assert bare_shared.zone_coord is None
    assert bare_shared.program_coord is coordinator
    assert bare_shared._program_names == DISHWASHER_NAMES

    bare_shared.client.get_raw_programs = AsyncMock(
        return_value=[{"id": 50, "name": "Eco", "status": "selected"}]
    )
    state = await bare_shared._fetch_programs()
    assert state.current["id"] == 50


@pytest.mark.asyncio
async def test_program_select():
    from custom_components.vzug.select import ProgramSelect

    coord = MagicMock(async_request_refresh=AsyncMock(), last_update_success=True)
    coord.data = zones.ProgramState(names=DISHWASHER_NAMES, current=None)
    shared = SimpleNamespace(
        program_coord=coord,
        client=MagicMock(set_program=AsyncMock()),
        unique_id_prefix="fc:1b:ff:06:01:da",
        device_info={},
    )
    select = ProgramSelect(shared)
    assert select.options == [
        "eco",
        "automatic",
        "quick",
        "intensive",
        "glass",
        "fondue_raclette",
        "hygiene",
        "pre_rinsing",
    ]
    assert select.current_option is None

    await select.async_select_option("quick")
    shared.client.set_program.assert_awaited_once_with(86)

    coord.data = zones.ProgramState(
        names=DISHWASHER_NAMES,
        current={"id": 50, "status": "selected", "duration": {"set": 21300}},
    )
    assert select.current_option == "eco"
    assert select.extra_state_attributes == {
        "status": "selected",
        "duration_seconds": 21300,
    }


@pytest.mark.asyncio
async def test_send_program_sends_what_the_app_sends():
    from custom_components.vzug.button import SendProgram

    eco = {
        "id": 50,
        "name": "Eco",
        "status": "selected",
        "starttime": {"min": 0, "max": 86400, "step": 600},
        "duration": {"set": 21300},
        "energySaving": {"set": False, "options": [True, False]},
        "optiStart": {"set": False},
        "partialload": {"set": False, "options": [True, False]},
        "rinsePlus": {"set": False, "options": [True, False]},
        "dryPlus": {"set": True, "options": [True, False]},
    }
    coord = MagicMock(
        async_request_refresh=AsyncMock(),
        async_refresh=AsyncMock(),
        last_update_success=True,
    )
    coord.data = zones.ProgramState(names=DISHWASHER_NAMES, current=eco)
    shared = SimpleNamespace(
        program_coord=coord,
        client=MagicMock(set_program=AsyncMock()),
        unique_id_prefix="fc:1b:ff:06:01:da",
        device_info={},
    )
    await SendProgram(shared).async_press()
    shared.client.set_program.assert_awaited_once_with(
        50,
        {
            "energySaving": False,
            "partialload": False,
            "rinsePlus": False,
            "dryPlus": True,
        },
    )

    coord.data = zones.ProgramState(names=DISHWASHER_NAMES, current=None)
    from homeassistant.exceptions import HomeAssistantError

    with pytest.raises(HomeAssistantError):
        await SendProgram(shared).async_press()
