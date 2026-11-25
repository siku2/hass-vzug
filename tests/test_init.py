"""Setting the integration up in a running Home Assistant, against simulated appliances."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .appliance import DEVICES, ApplianceNetwork
from .common import mock_entry


@pytest.mark.parametrize("device", DEVICES)
async def test_setup_and_unload(
    hass: HomeAssistant, appliances: ApplianceNetwork, device: str
) -> None:
    appliance = appliances.add(device)
    entry = mock_entry(appliance)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    device_entry = dr.async_get(hass).async_get_device(
        connections={(dr.CONNECTION_NETWORK_MAC, dr.format_mac(appliance.mac_address))}
    )
    assert device_entry is not None
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert entities
    assert all(e.device_id == device_entry.id for e in entities)
    assert len({e.unique_id for e in entities}) == len(entities)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_unreachable_appliance_retries_setup(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add("adora_dish_v6000")
    appliance.reachable = False
    entry = mock_entry(appliance)
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_wrong_credentials_start_reauth(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add("adora_dish_v6000", username="admin", password="secret")
    entry = mock_entry(appliance, password="wrong")
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_digest_credentials_work(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add("adora_dish_v6000", username="admin", password="secret")
    entry = mock_entry(appliance)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
