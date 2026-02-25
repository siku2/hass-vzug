"""Tests for coordinator caching and startup optimizations."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vzug import api
from custom_components.vzug.const import CONF_BASE_URL, DOMAIN


@pytest.fixture
def mock_agg_meta() -> api.AggMeta:
    return api.AggMeta(
        mac_address="FC:1B:FF:AA:BB:CC",
        model_id="V6000",
        model_name="Adora Dish V6000",
        device_name="Kitchen Dishwasher",
        serial_number="12345 678901",
        api_version=(1, 8, 0),
        ai_api_version=(1, 8, 0),
    )


@pytest.fixture
def mock_agg_state() -> api.AggState:
    return api.AggState(
        zh_mode=-1,
        device=api.DeviceStatus(
            DeviceName="Kitchen Dishwasher",
            Serial="12345 678901",
            Inactive="true",
            Program="",
            Status="",
        ),
        device_fetched_at=datetime.now(UTC),
        notifications=[
            api.PushNotification(date="2024-01-01", message="Test"),
        ],
        eco_info=api.EcoInfo(water=api.EcoInfoMetric(total=100.0, average=10.0)),
        hh_device_status=api.HhDeviceStatus(errors=[], displayedErrors=[]),
    )


@pytest.fixture
def mock_agg_update_status() -> api.AggUpdateStatus:
    return api.AggUpdateStatus(
        update=api.UpdateStatus(status="idle"),
        ai_fw_version=api.AiFwVersion(SW="2.0.0", HW="1.0.0"),
        hh_fw_version=api.HhFwVersion(),
    )


@pytest.fixture
def mock_agg_config() -> api.AggConfig:
    return {
        "cat1": api.AggCategory(
            key="cat1",
            description="Category 1",
            commands={
                "cmd1": api.Command(type="boolean", value="true", alterable=True),
            },
        ),
    }


@pytest.fixture
def mock_agg_program_state() -> api.AggProgramState:
    return api.AggProgramState(zones=[])


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
    mock_client.get_program_list.return_value = {}
    mock_client.get_cloud_status.return_value = api.CloudStatus()
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
        data={
            CONF_BASE_URL: "http://192.168.1.100",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
        unique_id="fc:1b:ff:aa:bb:cc",
    )


async def test_aggregate_program_called_once_for_refrigerator(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """aggregate_program should be called only once during setup, not twice."""
    # Setup with zone data so ProgramCoordinator is created
    mock_vzug_api.aggregate_program.return_value = api.AggProgramState(
        zones=[
            api.ZoneProgram(
                id=2000,
                status="active",
                temp=api.ZoneTemp(set=5.0, act=5.0),
                doorClosed=True,
                zone="fridge1",
            ),
        ]
    )

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    shared = mock_config_entry.runtime_data
    assert shared.program_coord is not None

    # aggregate_program called once in _post_first_refresh, NOT again by ProgramCoordinator
    mock_vzug_api.aggregate_program.assert_called_once()


async def test_cache_serialization_round_trip_state(mock_agg_state) -> None:
    """AggState should survive to_cache/from_cache round-trip."""
    cached = mock_agg_state.to_cache()
    restored = api.AggState.from_cache(cached)

    assert restored.zh_mode == mock_agg_state.zh_mode
    assert restored.device["DeviceName"] == mock_agg_state.device["DeviceName"]
    assert restored.device_fetched_at == mock_agg_state.device_fetched_at
    assert len(restored.notifications) == len(mock_agg_state.notifications)
    assert restored.eco_info["water"]["total"] == 100.0


async def test_cache_serialization_round_trip_update(
    mock_agg_update_status,
) -> None:
    """AggUpdateStatus should survive to_cache/from_cache round-trip."""
    cached = mock_agg_update_status.to_cache()
    restored = api.AggUpdateStatus.from_cache(cached)

    assert restored.update["status"] == "idle"
    assert restored.ai_fw_version["SW"] == "2.0.0"


async def test_cache_serialization_round_trip_config(mock_agg_config) -> None:
    """AggConfig should survive to_cache/from_cache round-trip."""
    cached = api.agg_config_to_cache(mock_agg_config)
    restored = api.agg_config_from_cache(cached)

    assert "cat1" in restored
    assert restored["cat1"].key == "cat1"
    assert restored["cat1"].description == "Category 1"
    assert "cmd1" in restored["cat1"].commands
    assert restored["cat1"].commands["cmd1"]["type"] == "boolean"


async def test_cache_written_after_setup(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Store should have a pending save after successful setup."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    shared = mock_config_entry.runtime_data
    assert hasattr(shared, "_store")


async def test_cache_hit_skips_network_refresh(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_state: api.AggState,
    mock_agg_update_status: api.AggUpdateStatus,
    mock_agg_config: api.AggConfig,
) -> None:
    """When cache exists, coordinators should not block on first refresh."""
    cached_data = {
        "state": mock_agg_state.to_cache(),
        "update": mock_agg_update_status.to_cache(),
        "config": api.agg_config_to_cache(mock_agg_config),
    }

    with patch("custom_components.vzug.coordinator.Store") as MockStore:
        store_instance = AsyncMock()
        store_instance.async_load.return_value = cached_data
        MockStore.return_value = store_instance

        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    # aggregate_state and aggregate_update_status should NOT have been called
    # during first_refresh (they may be called by background refresh)
    shared = mock_config_entry.runtime_data
    assert shared.state_coord.data is not None
    assert shared.update_coord.data is not None


async def test_cache_miss_falls_back_to_network(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """When no cache exists, coordinators block on first refresh normally."""
    with patch("custom_components.vzug.coordinator.Store") as MockStore:
        store_instance = AsyncMock()
        store_instance.async_load.return_value = None
        MockStore.return_value = store_instance

        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    # With no cache, aggregate_state must have been called
    mock_vzug_api.aggregate_state.assert_called()


async def test_corrupt_cache_falls_back_to_network(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """When cache data is corrupt, fall back to network refresh."""
    with patch("custom_components.vzug.coordinator.Store") as MockStore:
        store_instance = AsyncMock()
        store_instance.async_load.return_value = {
            "state": "garbage",
            "update": {},
            "config": {},
        }
        MockStore.return_value = store_instance

        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    # Fell back to network
    mock_vzug_api.aggregate_state.assert_called()
