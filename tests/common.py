"""Helpers for tests that run a real Home Assistant."""

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vzug.const import CONF_BASE_URL, DOMAIN

from .appliance import FakeAppliance


def mock_entry(appliance: FakeAppliance, **data: Any) -> MockConfigEntry:
    """A config entry for 'appliance', as the config flow creates it."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=2,
        title=appliance.device,
        unique_id=dr.format_mac(appliance.mac_address),
        data={
            "username": appliance.username,
            "password": appliance.password,
            CONF_BASE_URL: appliance.base_url,
            **data,
        },
    )


async def setup_appliance(
    hass: HomeAssistant, appliance: FakeAppliance, **data: Any
) -> MockConfigEntry:
    """Set up the integration for 'appliance' and wait until it is loaded."""
    entry = mock_entry(appliance, **data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry
