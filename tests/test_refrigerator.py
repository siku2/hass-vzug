"""Tests for refrigerator-specific entities (KS devices)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vzug import api
from custom_components.vzug.const import CONF_BASE_URL, DOMAIN
from custom_components.vzug.coordinator import Shared


@pytest.fixture
def mock_agg_meta() -> api.AggMeta:
    return api.AggMeta(
        mac_address="FC:1B:FF:AA:BB:CC",
        model_id="CCO4T-51108",
        model_name="CombiCooler V4000",
        device_name="Kitchen Refrigerator",
        serial_number="51108 116207",
        api_version=(1, 6, 0),
        ai_api_version=(1, 8, 0),
    )


@pytest.fixture
def mock_agg_state() -> api.AggState:
    return api.AggState(
        zh_mode=-1,
        device=api.DeviceStatus(
            DeviceName="Kitchen Refrigerator",
            Serial="51108 116207",
            Inactive="false",
            Program="",
            Status="",
        ),
        device_fetched_at=datetime.now(UTC),
        notifications=[],
        eco_info=api.EcoInfo(
            doorOpenings={
                "door0": {
                    "today": {"duration": 554, "amount": 20},
                    "7DayAvg": {"duration": 233, "amount": 17},
                    "30DayAvg": {"duration": 245, "amount": 19},
                },
                "door1": {
                    "today": {"duration": 60, "amount": 3},
                    "7DayAvg": {"duration": 7, "amount": 1},
                    "30DayAvg": {"duration": 8, "amount": 1},
                },
            }
        ),
    )


@pytest.fixture
def mock_agg_update_status() -> api.AggUpdateStatus:
    return api.AggUpdateStatus(
        update=api.UpdateStatus(status="idle"),
        ai_fw_version=api.AiFwVersion(SW="1052633-R20", HW="1009071-R09"),
        hh_fw_version=api.HhFwVersion(),
    )


@pytest.fixture
def mock_agg_program_state() -> api.AggProgramState:
    return api.AggProgramState(
        zones=[
            api.ZoneProgram(
                id=2000,
                status="active",
                temp=api.ZoneTemp(set=5.0, act=5.0, min=3.0, max=8.0),
                doorClosed=True,
                zone="fridge1",
            ),
            api.ZoneProgram(
                id=2001,
                status="active",
                temp=api.ZoneTemp(set=-18.0, act=-18.0, min=-24.0, max=-14.0),
                doorClosed=True,
                zone="freezer1",
            ),
            api.ZoneProgram(
                status="idle",
                zone="countdown1",
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
    mock_client.base_url = "http://192.168.1.100"

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
        data={CONF_BASE_URL: "http://192.168.1.100"},
        unique_id="fc:1b:ff:aa:bb:cc",
    )


async def test_refrigerator_setup(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that a refrigerator device sets up with program_coord."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    shared = mock_config_entry.runtime_data
    assert shared.program_coord is not None


async def test_door_opening_sensors_created(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that door opening eco sensors are created for refrigerators."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # door0 today amount (translation name: "Door Openings Today")
    state = hass.states.get(
        "sensor.kitchen_refrigerator_door_openings_today"
    )
    assert state is not None
    assert state.state == "20"

    # door0 today duration (translation name: "Door Open Duration Today")
    state = hass.states.get(
        "sensor.kitchen_refrigerator_door_open_duration_today"
    )
    assert state is not None
    assert state.state == "554"

    # door1 today amount (translation name: "Door 2 Openings Today")
    state = hass.states.get(
        "sensor.kitchen_refrigerator_door_2_openings_today"
    )
    assert state is not None
    assert state.state == "3"


async def test_zone_door_binary_sensors_created(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that zone door binary sensors are created."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # fridge door (doorClosed=True → is_on=False → "off")
    state = hass.states.get("binary_sensor.kitchen_refrigerator_fridge_door")
    assert state is not None
    assert state.state == "off"

    # freezer door (doorClosed=True → is_on=False → "off")
    state = hass.states.get("binary_sensor.kitchen_refrigerator_freezer_door")
    assert state is not None
    assert state.state == "off"

    # countdown1 has no doorClosed → no entity
    state = hass.states.get("binary_sensor.kitchen_refrigerator_countdown1_door")
    assert state is None


async def test_zone_temperature_sensors_created(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that zone temperature sensors are created."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # fridge actual temperature
    state = hass.states.get("sensor.kitchen_refrigerator_fridge_temperature")
    assert state is not None
    assert state.state == "5.0"

    # freezer actual temperature
    state = hass.states.get("sensor.kitchen_refrigerator_freezer_temperature")
    assert state is not None
    assert state.state == "-18.0"


async def test_non_refrigerator_no_program_coord(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_program_state: api.AggProgramState,
) -> None:
    """Test that non-refrigerator devices don't get program_coord."""
    # Simulate a non-refrigerator that has no zone data
    mock_agg_program_state.zones = []
    mock_vzug_api.aggregate_program.return_value = mock_agg_program_state

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    shared = mock_config_entry.runtime_data
    assert shared.program_coord is None


async def test_unload_with_program_coord(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that unloading works with program_coord."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
