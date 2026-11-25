"""How the integration follows an appliance over time, in a running Home Assistant."""

import httpx
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.vzug import coordinator

from .appliance import ApplianceNetwork
from .common import setup_appliance

DISHWASHER = "adora_dish_v6000"


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta) -> None:
    """Let 'delta' pass: for the clock the coordinators read, and for their timers."""
    freezer.tick(delta)
    async_fire_time_changed(hass)
    # the coordinators refresh in background tasks
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_running_program(
    hass: HomeAssistant, appliances: ApplianceNetwork, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-01-15 12:00:30+00:00")
    appliance = appliances.add(DISHWASHER)
    status = appliance.response_json("ai_get_devicestatus.json")
    await setup_appliance(hass, appliance)
    assert hass.states.get("sensor.adora_sl_program").state == "standby"
    assert hass.states.get("sensor.adora_sl_program_end").state == "unknown"

    # someone starts 'Eco' at the appliance, 1h30 to go
    running = {
        **status,
        "Inactive": "false",
        "Program": "Eco",
        "ProgramEnd": {"End": "1h30", "EndType": "1"},
    }
    appliance.set_json("ai", "getDeviceStatus", running)
    await _tick(hass, freezer, coordinator.STATE_COORD_IDLE_PROBE_INTERVAL)

    assert hass.states.get("sensor.adora_sl_program").state == "Eco"
    end = hass.states.get("sensor.adora_sl_program_end").state
    assert end == "2026-01-15T13:35:00+00:00"

    # a few minutes later, the end only moves by what the appliance reports
    appliance.set_json(
        "ai",
        "getDeviceStatus",
        {**running, "ProgramEnd": {"End": "1h25", "EndType": "1"}},
    )
    await _tick(hass, freezer, coordinator.STATE_COORD_ACTIVE_INTERVAL)
    assert hass.states.get("sensor.adora_sl_program_end").state == end

    # it is done
    appliance.set_json("ai", "getDeviceStatus", status)
    await _tick(hass, freezer, coordinator.STATE_COORD_ACTIVE_INTERVAL)
    assert hass.states.get("sensor.adora_sl_program").state == "standby"
    assert hass.states.get("sensor.adora_sl_program_end").state == "unknown"


async def test_standby_leaves_the_appliance_alone(
    hass: HomeAssistant, appliances: ApplianceNetwork, freezer: FrozenDateTimeFactory
) -> None:
    appliance = appliances.add(DISHWASHER)
    await setup_appliance(hass, appliance)

    appliance.calls.clear()
    await _tick(hass, freezer, coordinator.STATE_COORD_IDLE_INTERVAL)
    # only the AI module is asked, 'getDeviceStatus' would wake the appliance
    assert appliance.commands("ai") == ["getLastPUSHNotifications"]
    assert "getDeviceStatus" not in appliance.commands()


async def test_unreachable_appliance_becomes_unavailable(
    hass: HomeAssistant, appliances: ApplianceNetwork, freezer: FrozenDateTimeFactory
) -> None:
    appliance = appliances.add(DISHWASHER)
    await setup_appliance(hass, appliance)
    assert hass.states.get("sensor.adora_sl_last_notification").state != "unavailable"

    appliance.reachable = False
    await _tick(hass, freezer, coordinator.STATE_COORD_IDLE_INTERVAL)
    assert hass.states.get("sensor.adora_sl_last_notification").state == "unavailable"

    appliance.reachable = True
    await _tick(hass, freezer, coordinator.STATE_COORD_IDLE_INTERVAL)
    assert hass.states.get("sensor.adora_sl_last_notification").state != "unavailable"


async def test_busy_config_tree_keeps_the_settings(
    hass: HomeAssistant, appliances: ApplianceNetwork, freezer: FrozenDateTimeFactory
) -> None:
    """A busy appliance answers 'getCategories' with '[]', that must not stick."""
    appliance = appliances.add(DISHWASHER)
    await setup_appliance(hass, appliance)
    entity_id = "switch.adora_sl_kindersicherung"
    before = hass.states.get(entity_id).state

    appliance.set_json("hh", "getCategories", [])
    for _ in range(coordinator.CONFIG_MAX_STALE_UPDATES):
        await _tick(hass, freezer, coordinator.CONFIG_COORD_INTERVAL)
        assert hass.states.get(entity_id).state == before

    await _tick(hass, freezer, coordinator.CONFIG_COORD_INTERVAL)
    assert hass.states.get(entity_id).state == "unavailable"


async def test_program_poll_keeps_the_selection_on_errors(
    hass: HomeAssistant, appliances: ApplianceNetwork, freezer: FrozenDateTimeFactory
) -> None:
    appliance = appliances.add(DISHWASHER)
    await setup_appliance(hass, appliance)
    entity_id = "select.adora_sl_program_selection"
    before = hass.states.get(entity_id).state

    appliance.set_response("hh", "getProgram", httpx.Response(503))
    await _tick(hass, freezer, coordinator.PROGRAM_COORD_INTERVAL)
    assert hass.states.get(entity_id).state == before


async def test_new_setting_becomes_an_entity(
    hass: HomeAssistant, appliances: ApplianceNetwork, freezer: FrozenDateTimeFactory
) -> None:
    """A setting the appliance lists later (ex. after an update) gets its entity."""
    appliance = appliances.add("combi_cooler_v4000")
    await setup_appliance(hass, appliance)
    assert hass.states.get("switch.kuhlschrank_eco_modus") is None

    categories = appliance.response_json("hh_get_categories.json")
    categories[0]["commands"].append("ECO_MODE")
    details = {
        "type": "boolean",
        "description": "Eco-Modus",
        "command": "ECO_MODE",
        "value": "true",
        "alterable": True,
    }

    def categories_answer(command: str):
        def answer(value: str | None) -> httpx.Response:
            if command == "getCategories":
                return httpx.Response(200, json=[c["id"] for c in categories])
            return httpx.Response(200, json=categories[0]["commands"])

        return answer

    def command_answer(value: str | None) -> httpx.Response:
        if value == "ECO_MODE":
            return httpx.Response(200, json=details)
        return appliance._answer_hh("getCommand", value)

    appliance.set_response("hh", "getCategories", categories_answer("getCategories"))
    appliance.set_response("hh", "getCommands", categories_answer("getCommands"))
    appliance.set_response("hh", "getCommand", command_answer)
    await _tick(hass, freezer, coordinator.CONFIG_COORD_INTERVAL)

    assert hass.states.get("switch.kuhlschrank_eco_modus").state == "on"
    # the others are still there, once
    assert len(hass.states.async_entity_ids("switch")) == len(
        set(hass.states.async_entity_ids("switch"))
    )
    assert hass.states.get("switch.kuhlschrank_turalarm").state == "on"
