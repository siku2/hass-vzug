"""Tests for new entities: errors, cloud, program select, zone features, update attrs."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vzug import api

# ── Dishwasher (default) fixtures ──────────────────────────────────


async def test_has_errors_binary_sensor_no_errors(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test has_errors binary sensor shows off when no errors."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.kitchen_dishwasher_has_errors")
    assert state is not None
    assert state.state == "off"


async def test_has_errors_binary_sensor_with_errors(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_state: api.AggState,
) -> None:
    """Test has_errors binary sensor shows on when errors present."""
    mock_agg_state.hh_device_status = api.HhDeviceStatus(
        errors=[{"displayCode": "E01", "errorDescriptionUser": "Test error"}],
    )

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.kitchen_dishwasher_has_errors")
    assert state is not None
    assert state.state == "on"


async def test_has_errors_binary_sensor_displayed_errors_only(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_state: api.AggState,
) -> None:
    """Test has_errors detects displayedErrors (may be absent on some devices)."""
    mock_agg_state.hh_device_status = api.HhDeviceStatus(
        displayedErrors=[{"displayCode": "E02"}],
    )

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.kitchen_dishwasher_has_errors")
    assert state is not None
    assert state.state == "on"


async def test_has_errors_bo_no_displayed_errors_field(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_state: api.AggState,
) -> None:
    """Test BO (oven) that omits displayedErrors entirely."""
    mock_agg_state.hh_device_status = api.HhDeviceStatus(errors=[])

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.kitchen_dishwasher_has_errors")
    assert state is not None
    assert state.state == "off"


async def test_active_errors_sensor_registered(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_state: api.AggState,
) -> None:
    """Test active_errors sensor is registered (disabled by default)."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get("sensor.kitchen_dishwasher_active_errors")
    assert entry is not None
    assert entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION


async def test_cloud_connected_binary_sensor_registered(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test cloud connected sensor is registered (disabled by default)."""
    mock_vzug_api.get_cloud_status.return_value = api.CloudStatus(
        enabled=True, claimed=True, status="connected"
    )

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get("binary_sensor.kitchen_dishwasher_cloud_connected")
    assert entry is not None
    assert entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION


async def test_program_select_entity(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test program select entity with named programs."""
    mock_vzug_api.get_program_list.return_value = {
        50: "Eco",
        51: "Automatic",
        54: "Intensive",
    }

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("select.kitchen_dishwasher_program")
    assert state is not None
    assert "Eco" in state.attributes["options"]
    assert "Automatic" in state.attributes["options"]
    assert "Intensive" in state.attributes["options"]


async def test_program_select_not_created_when_empty(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test program select is not created when no programs available."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("select.kitchen_dishwasher_program")
    assert state is None


async def test_update_extra_attributes(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_update_status: api.AggUpdateStatus,
) -> None:
    """Test update entity has status and isSynced attributes."""
    mock_agg_update_status.update = api.UpdateStatus(status="idle", isSynced=True)

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("update.kitchen_dishwasher_update")
    assert state is not None
    assert state.attributes["update_status"] == "idle"
    assert state.attributes["is_synced"] is True


async def test_water_option_sensor_not_created_without_water(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test water_option sensor is not created for devices without water eco info."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_dishwasher_water_option")
    assert state is None
