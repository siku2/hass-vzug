"""Actions on the entities, in a running Home Assistant, against simulated appliances."""

import json
from typing import Any

import httpx
import pytest
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.components.update import SERVICE_INSTALL
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .appliance import ApplianceNetwork, FakeAppliance
from .common import setup_appliance

COOLER = "combi_cooler_v4000"
DISHWASHER = "adora_dish_v6000"
STEAMER = "combair_steamer_v6000_76c"


async def _call(
    hass: HomeAssistant, domain: str, service: str, entity_id: str, **data: Any
) -> None:
    await hass.services.async_call(
        domain, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
    )
    await hass.async_block_till_done()


def _writes(appliance: FakeAppliance) -> list[tuple[str, str | None]]:
    """(command, value) of everything sent to the appliance, values decoded."""
    result = []
    for call in appliance.writes():
        value: Any = call.value
        if value and value.startswith("{"):
            value = json.loads(value)
        result.append((call.command, value))
    return result


def _clear(appliance: FakeAppliance) -> None:
    appliance.calls.clear()


@pytest.fixture
async def cooler(hass: HomeAssistant, appliances: ApplianceNetwork) -> FakeAppliance:
    appliance = appliances.add(COOLER)
    await setup_appliance(hass, appliance)
    _clear(appliance)
    return appliance


@pytest.mark.parametrize(
    ("domain", "service", "entity_id", "data", "expected"),
    [
        (
            "switch",
            SERVICE_TURN_ON,
            "switch.kuhlschrank_holiday_mode",
            {},
            [("setcmdHolidayMode", "true")],
        ),
        (
            "switch",
            SERVICE_TURN_OFF,
            "switch.kuhlschrank_silentplus",
            {},
            [("setcmdSilentPlusMode", "false")],
        ),
        (
            "switch",
            SERVICE_TURN_ON,
            "switch.kuhlschrank_supercool",
            {},
            [("setProgram", {"zone": "fridge1", "superCool": "43200"})],
        ),
        (
            "switch",
            SERVICE_TURN_OFF,
            "switch.kuhlschrank_superfreeze",
            {},
            [("setProgram", {"zone": "freezer1", "superFreeze": "0"})],
        ),
        (
            "number",
            SERVICE_SET_VALUE,
            "number.kuhlschrank_fridge_temperature",
            {ATTR_VALUE: 7},
            [("setProgram", {"zone": "fridge1", "temp": "7"})],
        ),
        (
            "number",
            SERVICE_SET_VALUE,
            "number.kuhlschrank_timer",
            {ATTR_VALUE: 5},
            [("setProgram", {"zone": "countdown1", "duration": "300"})],
        ),
        (
            "select",
            SERVICE_SELECT_OPTION,
            "select.kuhlschrank_temperature_unit",
            {ATTR_OPTION: "°F"},
            [("setcmdTemperatureUnit", "°F")],
        ),
        (
            "switch",
            SERVICE_TURN_OFF,
            "switch.kuhlschrank_turalarm",
            {},
            [("setDOOR_ALARM", "false")],
        ),
        (
            "number",
            SERVICE_SET_VALUE,
            "number.kuhlschrank_helligkeit",
            {ATTR_VALUE: 4},
            [("setBRIGHTNESS", "4")],
        ),
        (
            "select",
            SERVICE_SELECT_OPTION,
            "select.kuhlschrank_sprache",
            {ATTR_OPTION: "English"},
            [("setLANGUAGE", "English")],
        ),
        (
            "button",
            SERVICE_PRESS,
            "button.kuhlschrank_filter_zurucksetzen",
            {},
            [("doRESET_FILTER", None)],
        ),
        (
            "button",
            SERVICE_PRESS,
            "button.kuhlschrank_check_for_updates",
            {},
            [("checkUpdate", None)],
        ),
    ],
)
async def test_cooler_actions(
    hass: HomeAssistant,
    cooler: FakeAppliance,
    domain: str,
    service: str,
    entity_id: str,
    data: dict,
    expected: list,
) -> None:
    await _call(hass, domain, service, entity_id, **data)
    assert _writes(cooler) == expected


async def test_cooler_mode_follows_the_appliance(
    hass: HomeAssistant, cooler: FakeAppliance
) -> None:
    await _call(hass, "switch", SERVICE_TURN_ON, "switch.kuhlschrank_holiday_mode")
    assert hass.states.get("switch.kuhlschrank_holiday_mode").state == "on"


async def test_boost_duration_is_sent_with_the_switch(
    hass: HomeAssistant, cooler: FakeAppliance
) -> None:
    await _call(
        hass,
        "number",
        SERVICE_SET_VALUE,
        "number.kuhlschrank_supercool_duration",
        **{ATTR_VALUE: 3},
    )
    assert _writes(cooler) == []
    assert hass.states.get("number.kuhlschrank_supercool_duration").state == "3.0"

    await _call(hass, "switch", SERVICE_TURN_ON, "switch.kuhlschrank_supercool")
    assert _writes(cooler) == [
        ("setProgram", {"zone": "fridge1", "superCool": "10800"})
    ]


async def test_refresh_now_wakes_the_appliance(
    hass: HomeAssistant, cooler: FakeAppliance
) -> None:
    await _call(hass, "button", SERVICE_PRESS, "button.kuhlschrank_refresh_now")
    assert "getDeviceStatus" in cooler.commands("ai")
    assert "getCategories" in cooler.commands("hh")


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(400, text="400.03"), "refused the request: 400 400.03"),
        (httpx.ConnectError("unreachable"), "Error communicating with the appliance"),
        (httpx.Response(200, json={"error": "busy"}), None),
    ],
)
async def test_failed_action_is_reported(
    hass: HomeAssistant, cooler: FakeAppliance, response: Any, message: str | None
) -> None:
    cooler.set_response("hh", "setcmdHolidayMode", response)
    if message is None:
        # a raw command doesn't look at the body
        await _call(hass, "switch", SERVICE_TURN_ON, "switch.kuhlschrank_holiday_mode")
        return
    with pytest.raises(HomeAssistantError, match=message):
        await _call(hass, "switch", SERVICE_TURN_ON, "switch.kuhlschrank_holiday_mode")


async def test_refused_credentials_start_reauth(
    hass: HomeAssistant, cooler: FakeAppliance
) -> None:
    cooler.set_response("hh", "setcmdHolidayMode", httpx.Response(401))
    with pytest.raises(HomeAssistantError, match="Re-authenticate"):
        await _call(hass, "switch", SERVICE_TURN_ON, "switch.kuhlschrank_holiday_mode")
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


ECO_SELECTED = [
    {
        "id": 50,
        "name": "Eco",
        "status": "selected",
        "starttime": {"min": 0, "max": 86400, "step": 600},
        "duration": {"set": 22440},
        "energySaving": {"set": False, "options": [True, False]},
        "steamfinish": {"set": True, "options": [True, False]},
    }
]


@pytest.fixture
async def dishwasher(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> FakeAppliance:
    appliance = appliances.add(DISHWASHER)
    await setup_appliance(hass, appliance)
    _clear(appliance)
    return appliance


async def test_select_and_send_program(
    hass: HomeAssistant, dishwasher: FakeAppliance
) -> None:
    def get_program(value: str | None) -> httpx.Response:
        return httpx.Response(200, json=ECO_SELECTED)

    await _call(
        hass,
        "select",
        SERVICE_SELECT_OPTION,
        "select.adora_sl_program_selection",
        **{ATTR_OPTION: "eco"},
    )
    assert _writes(dishwasher) == [("setProgram", {"id": 50})]

    dishwasher.set_response("hh", "getProgram", get_program)
    _clear(dishwasher)
    await _call(
        hass,
        "number",
        SERVICE_SET_VALUE,
        "number.adora_sl_start_delay",
        **{ATTR_VALUE: 2},
    )
    await _call(hass, "button", SERVICE_PRESS, "button.adora_sl_send_to_appliance")
    assert _writes(dishwasher) == [
        (
            "setProgram",
            {
                "id": 50,
                "energySaving": False,
                "steamfinish": True,
                "starttime": 7200,
            },
        )
    ]
    assert hass.states.get("select.adora_sl_program_selection").state == "eco"
    # the delay was for this one program
    assert hass.states.get("number.adora_sl_start_delay").state == "0.0"


async def test_send_without_a_program(
    hass: HomeAssistant, dishwasher: FakeAppliance
) -> None:
    with pytest.raises(HomeAssistantError, match="Select a program first"):
        await _call(hass, "button", SERVICE_PRESS, "button.adora_sl_send_to_appliance")
    assert _writes(dishwasher) == []


async def test_unknown_program(hass: HomeAssistant, dishwasher: FakeAppliance) -> None:
    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            "select",
            SERVICE_SELECT_OPTION,
            "select.adora_sl_program_selection",
            **{ATTR_OPTION: "nope"},
        )


async def test_stop_and_start_program(
    hass: HomeAssistant, dishwasher: FakeAppliance
) -> None:
    await _call(hass, "button", SERVICE_PRESS, "button.adora_sl_stop")
    assert _writes(dishwasher) == [("setProgram", {"status": "idle"})]

    registry = er.async_get(hass)
    entity_id = "button.adora_sl_start_program_experimental"
    entry = registry.async_get(entity_id)
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.config_entry_id)
    await hass.async_block_till_done()

    _clear(dishwasher)
    dishwasher.set_response(
        "hh", "setProgram", httpx.Response(400, text='{"code":"400.04"}')
    )
    with pytest.raises(HomeAssistantError, match="400.04"):
        await _call(hass, "button", SERVICE_PRESS, entity_id)
    assert _writes(dishwasher) == [("setProgram", {"status": "active"})]


async def test_install_update(hass: HomeAssistant, dishwasher: FakeAppliance) -> None:
    status = dishwasher.response_json("ai_get_updatestatus.json")
    status["isAIUpdateAvailable"] = True
    status["components"][0]["available"] = True
    dishwasher.set_json("ai", "getUpdateStatus", status)
    await _call(hass, "button", SERVICE_PRESS, "button.adora_sl_check_for_updates")
    assert hass.states.get("update.adora_sl_update").state == "on"

    _clear(dishwasher)
    await _call(hass, "update", SERVICE_INSTALL, "update.adora_sl_update")
    assert ("doAIUpdate", None) in _writes(dishwasher)


@pytest.fixture
async def steamer(hass: HomeAssistant, appliances: ApplianceNetwork) -> FakeAppliance:
    appliance = appliances.add(STEAMER)
    await setup_appliance(hass, appliance)
    _clear(appliance)
    return appliance


@pytest.mark.parametrize(
    ("domain", "service", "entity_id", "data", "expected"),
    [
        (
            "switch",
            SERVICE_TURN_ON,
            "switch.combairsteamer_v6000_76c_oven_light",
            {},
            [("setProgram", {"zone": "cookingChamber1", "light": True})],
        ),
        (
            "number",
            SERVICE_SET_VALUE,
            "number.combairsteamer_v6000_76c_timer",
            {ATTR_VALUE: 10},
            [
                (
                    "setProgram",
                    {
                        "zone": "countdown1",
                        "id": 9000,
                        "status": "active",
                        "duration": 600,
                    },
                )
            ],
        ),
        (
            "number",
            SERVICE_SET_VALUE,
            "number.combairsteamer_v6000_76c_timer",
            {ATTR_VALUE: 0},
            [("setProgram", {"status": "idle", "zone": "countdown1"})],
        ),
        (
            "button",
            SERVICE_PRESS,
            "button.combairsteamer_v6000_76c_stop_2",
            {},
            [("setProgram", {"status": "idle", "zone": "cookingChamber1"})],
        ),
        (
            "button",
            SERVICE_PRESS,
            "button.combairsteamer_v6000_76c_start_warming_drawer",
            {},
            [
                (
                    "setProgram",
                    {
                        "id": 103,
                        "zone": "warmingDrawer1",
                        "duration": 7200,
                        "status": "selected",
                    },
                )
            ],
        ),
    ],
)
async def test_steamer_actions(
    hass: HomeAssistant,
    steamer: FakeAppliance,
    domain: str,
    service: str,
    entity_id: str,
    data: dict,
    expected: list,
) -> None:
    await _call(hass, domain, service, entity_id, **data)
    assert _writes(steamer) == expected


async def test_update_progress(hass: HomeAssistant, dishwasher: FakeAppliance) -> None:
    status = dishwasher.response_json("ai_get_updatestatus.json")
    status.update(status="downloading", isAIUpdateAvailable=True)
    status["components"][0].update(
        available=True, running=True, progress={"download": 100, "installation": 20}
    )
    dishwasher.set_json("ai", "getUpdateStatus", status)
    await _call(hass, "button", SERVICE_PRESS, "button.adora_sl_check_for_updates")

    state = hass.states.get("update.adora_sl_update")
    assert state.attributes["in_progress"] is True
    assert state.attributes["update_percentage"] == 60
