"""Tests for oven-specific entities (BO devices with cooking zones)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vzug import api
from custom_components.vzug.const import CONF_BASE_URL, DOMAIN


@pytest.fixture
def mock_agg_meta() -> api.AggMeta:
    return api.AggMeta(
        mac_address="FC:1B:FF:AA:BB:DD",
        model_id="BCSESL60",
        model_name="Combair SE SL 60",
        device_name="Kitchen Oven",
        serial_number="99999 123456",
        api_version=(1, 11, 0),
        ai_api_version=(1, 8, 0),
    )


@pytest.fixture
def mock_agg_state() -> api.AggState:
    return api.AggState(
        zh_mode=-1,
        device=api.DeviceStatus(
            DeviceName="Kitchen Oven",
            Serial="99999 123456",
            Inactive="false",
            Program="Convection",
            Status="Preheating",
        ),
        device_fetched_at=datetime.now(UTC),
        notifications=[],
        eco_info=api.EcoInfo(energy=api.EcoInfoMetric(total=277.0, program=1.5)),
        hh_device_status=api.HhDeviceStatus(
            errors=[], notifications=[], isUpdatePossible=True
        ),
    )


@pytest.fixture
def mock_agg_update_status() -> api.AggUpdateStatus:
    return api.AggUpdateStatus(
        update=api.UpdateStatus(status="idle"),
        ai_fw_version=api.AiFwVersion(SW="2.0.0", HW="1.0.0"),
        hh_fw_version=api.HhFwVersion(),
    )


@pytest.fixture
def mock_agg_program_state() -> api.AggProgramState:
    return api.AggProgramState(
        zones=[
            api.ZoneProgram(
                id=100,
                status="active",
                zone="cookingChamber1",
                temp=api.ZoneTemp(set=200.0, act=175.0, min=30.0, max=300.0),
                doorClosed=True,
                light={"set": True},
                preheatStatus={"set": True},
                probeInserted={"act": False},
            ),
        ]
    )


@pytest.fixture
def mock_agg_config() -> api.AggConfig:
    return {}


@pytest.fixture
def mock_vzug_api(
    mock_agg_meta,
    mock_agg_state,
    mock_agg_update_status,
    mock_agg_config,
    mock_agg_program_state,
) -> AsyncMock:
    mock_client = AsyncMock(spec=api.VZugApi)
    mock_client.aggregate_meta.return_value = mock_agg_meta
    mock_client.aggregate_state.return_value = mock_agg_state
    mock_client.aggregate_update_status.return_value = mock_agg_update_status
    mock_client.aggregate_config.return_value = mock_agg_config
    mock_client.aggregate_program.return_value = mock_agg_program_state
    mock_client.get_program_list.return_value = {}  # BO doesn't support setProgram
    mock_client.get_cloud_status.return_value = api.CloudStatus(
        enabled=True, claimed=True, status="connected"
    )
    mock_client.base_url = "http://192.168.1.200"

    with patch(
        "custom_components.vzug.api.VZugApi", return_value=mock_client
    ) as mock_cls:
        mock_cls.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=2,
        data={CONF_BASE_URL: "http://192.168.1.200"},
        unique_id="fc:1b:ff:aa:bb:dd",
    )


async def test_oven_setup_with_zone_entities(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that oven zone entities are created when zone data has light/preheat/probe."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    shared = mock_config_entry.runtime_data
    assert shared.program_coord is not None


async def test_oven_zone_light(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test cooking chamber light binary sensor."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.kitchen_oven_cooking_chamber_light")
    assert state is not None
    assert state.state == "on"


async def test_oven_zone_preheat(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test cooking chamber preheat binary sensor."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.kitchen_oven_cooking_chamber_preheat")
    assert state is not None
    assert state.state == "on"


async def test_oven_zone_probe(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test cooking chamber probe inserted binary sensor."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.kitchen_oven_cooking_chamber_probe")
    assert state is not None
    assert state.state == "off"


async def test_oven_zone_door(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test cooking chamber door binary sensor."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.kitchen_oven_cooking_chamber_door")
    assert state is not None, (
        f"Expected cooking chamber door entity; available: "
        f"{[s.entity_id for s in hass.states.async_all() if 'door' in s.entity_id]}"
    )
    # doorClosed=True → is_on=False → "off"
    assert state.state == "off"


async def test_oven_zone_temperature(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test cooking chamber temperature sensors."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # temperature_cookingChamber1 has no translation, gets generic name "Temperature"
    state = hass.states.get("sensor.kitchen_oven_temperature")
    assert state is not None
    assert state.state == "175.0"


async def test_oven_no_program_select(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test program select is NOT created for oven (sendProgramSupported=false)."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("select.kitchen_oven_program")
    assert state is None


async def test_oven_no_zone_features_when_absent(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_program_state: api.AggProgramState,
) -> None:
    """Test that zone entities are not created when keys are absent."""
    # Remove light, preheat, probe from zone data (idle oven)
    mock_agg_program_state.zones = [
        api.ZoneProgram(
            status="idle",
            zone="cookingChamber1",
            temp=api.ZoneTemp(set=0.0, act=25.0, min=30.0, max=300.0),
            doorClosed=True,
        ),
    ]
    mock_vzug_api.aggregate_program.return_value = mock_agg_program_state

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # Light, preheat, probe should not exist
    assert hass.states.get("binary_sensor.kitchen_oven_cooking_chamber_light") is None
    assert hass.states.get("binary_sensor.kitchen_oven_cooking_chamber_preheat") is None
    assert hass.states.get("binary_sensor.kitchen_oven_cooking_chamber_probe") is None

    # Door should still exist
    assert (
        hass.states.get("binary_sensor.kitchen_oven_cooking_chamber_door") is not None
    )


async def test_oven_program_sensor_translates_german(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_state: api.AggState,
) -> None:
    """Test program sensor translates German firmware text to English."""
    mock_agg_state.device = api.DeviceStatus(
        DeviceName="Kitchen Oven",
        Serial="99999 123456",
        Inactive="true",
        Program="Keine Betriebsart",
        Status="",
    )

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_oven_program")
    assert state is not None
    assert state.state == "No Operating Mode"


async def test_oven_program_sensor_resolves_active_zone_id(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_state: api.AggState,
    mock_agg_program_state: api.AggProgramState,
) -> None:
    """Test program sensor resolves active zone program ID to English name."""
    # Oven is running Hot Air (program ID 4) but firmware returns German
    mock_agg_state.device = api.DeviceStatus(
        DeviceName="Kitchen Oven",
        Serial="99999 123456",
        Inactive="false",
        Program="Heissluft",
        Status="",
    )
    mock_agg_program_state.zones = [
        api.ZoneProgram(
            id=4,
            status="active",
            zone="cookingChamber1",
            temp=api.ZoneTemp(set=200.0, act=175.0, min=30.0, max=300.0),
            doorClosed=True,
        ),
    ]
    mock_vzug_api.aggregate_program.return_value = mock_agg_program_state

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_oven_program")
    assert state is not None
    # Should resolve program ID 4 → "Hot Air" via PROGRAM_NAMES, not "Heissluft"
    assert state.state == "Hot Air"
