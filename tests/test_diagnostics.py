"""Diagnostics of a config entry."""

import json
import re

import httpx
import pytest
from homeassistant.config_entries import DiscoveryKey
from homeassistant.core import HomeAssistant
from pytest_homeassistant.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion
from syrupy.filters import props

from .appliance import DEVICES, ApplianceNetwork
from .common import mock_entry, setup_appliance


@pytest.mark.parametrize("device", DEVICES)
async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    appliances: ApplianceNetwork,
    snapshot: SnapshotAssertion,
    device: str,
) -> None:
    appliance = appliances.add(device, username="admin", password="secret")
    entry = await setup_appliance(hass, appliance)

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    # the cache buster in the URLs of failed requests
    diagnostics = json.loads(re.sub(r"_=\d+", "_=0", json.dumps(diagnostics)))

    assert diagnostics == snapshot(
        exclude=props("entry_id", "created_at", "modified_at")
    )
    # nothing that identifies the appliance is left
    text = json.dumps(diagnostics)
    serial = appliance.response_json("ai_get_fwversion.json")["fn"]
    for secret in (appliance.host, appliance.mac_address, serial, "secret", "admin"):
        assert secret not in text


async def test_diagnostics_with_failing_commands(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    appliances: ApplianceNetwork,
) -> None:
    appliance = appliances.add("adora_dish_v6000")
    entry = await setup_appliance(hass, appliance)
    appliance.set_response("hh", "getDeviceInfo", httpx.Response(500))

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    error = diagnostics["api_sample"]["device_info"]
    assert error["type"] == "HTTPStatusError"
    assert "**REDACTED**" in error["message"]
    assert appliance.host not in json.dumps(diagnostics)
    assert diagnostics["coordinators"]["state"]["last_update_success"] is True


async def test_diagnostics_redact_the_discovery_keys(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    appliances: ApplianceNetwork,
) -> None:
    appliance = appliances.add("adora_dish_v6000")
    mac = appliance.mac_address.replace(":", "").lower()
    entry = mock_entry(appliance)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        discovery_keys={"dhcp": (DiscoveryKey(domain="dhcp", key=mac, version=1),)},
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert mac not in json.dumps(diagnostics)
