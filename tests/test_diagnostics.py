"""Diagnostics of a config entry."""

import httpx
from homeassistant.core import HomeAssistant
from pytest_homeassistant.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant.typing import ClientSessionGenerator

from .appliance import ApplianceNetwork
from .common import setup_appliance


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    appliances: ApplianceNetwork,
) -> None:
    appliance = appliances.add("adora_dish_v6000", username="admin", password="secret")
    entry = await setup_appliance(hass, appliance)
    appliance.set_response("hh", "getErrors", httpx.ConnectError("gone"))
    appliance.set_response("hh", "getDeviceInfo", httpx.Response(500))

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diagnostics["entry"]["data"]["username"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["password"] == "**REDACTED**"
    sample = diagnostics["api_sample"]
    assert sample["model_description"] == "AdoraDish V6000 Emulator"
    assert sample["zh_mode"] == 2
    assert sample["device_info"]["type"] == "HTTPStatusError"
    assert "CATEGORY_0" in sample["aggregate_config"]
