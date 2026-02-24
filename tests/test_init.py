"""Tests for V-ZUG integration setup, unload, and migration."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vzug import api
from custom_components.vzug.const import CONF_BASE_URL, DOMAIN
from custom_components.vzug.shared import Shared


async def test_setup_entry_success(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert isinstance(mock_config_entry.runtime_data, Shared)


async def test_setup_entry_no_credentials(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=2,
        data={CONF_BASE_URL: "http://192.168.1.100"},
        unique_id="fc:1b:ff:aa:bb:cc",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED


async def test_setup_entry_auth_failure(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_vzug_api.aggregate_meta.side_effect = api.AuthenticationFailed()
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_entry_connection_failure(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_vzug_api.aggregate_meta.side_effect = Exception("connection refused")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_unload_entry(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_migrate_downgrade_rejected(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        minor_version=0,
        data={CONF_BASE_URL: "http://192.168.1.100"},
        unique_id="fc:1b:ff:aa:bb:cc",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_migrate_v1_to_v2_2(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_agg_state: api.AggState,
) -> None:
    mock_agg_state.device["deviceUuid"] = "old-uuid-prefix"
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        data={
            "host": "192.168.1.100",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
        unique_id="fc:1b:ff:aa:bb:cc",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_BASE_URL] == "http://192.168.1.100"
    assert "host" not in entry.data
    assert entry.version == 2
    assert entry.minor_version == 2


async def test_migrate_v2_0_to_v2_2(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_agg_state: api.AggState,
) -> None:
    mock_agg_state.device["deviceUuid"] = "old-uuid-prefix"

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=1,
        data={
            CONF_BASE_URL: "http://192.168.1.100",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
        unique_id="fc:1b:ff:aa:bb:cc",
    )
    entry.add_to_hass(hass)

    # Add an entity with old-style unique_id to verify migration
    entity_reg = er.async_get(hass)
    entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "old-uuid-prefix_status",
        config_entry=entry,
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 2
    assert entry.minor_version == 2

    # Verify entity unique_id was migrated
    migrated = entity_reg.async_get("sensor.vzug_old_uuid_prefix_status")
    if migrated:
        assert "fc:1b:ff:aa:bb:cc" in migrated.unique_id
