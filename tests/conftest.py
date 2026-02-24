"""Shared fixtures for V-ZUG HA-level tests."""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vzug import api
from custom_components.vzug.const import CONF_BASE_URL, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations for all tests."""
    return


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
        notifications=[],
        eco_info=api.EcoInfo(),
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
    return {}


@pytest.fixture
def mock_agg_program_state() -> api.AggProgramState:
    """Default: no zones (non-refrigerator device)."""
    return api.AggProgramState(zones=[])


@pytest.fixture
def mock_vzug_api(
    mock_agg_meta: api.AggMeta,
    mock_agg_state: api.AggState,
    mock_agg_update_status: api.AggUpdateStatus,
    mock_agg_config: api.AggConfig,
    mock_agg_program_state: api.AggProgramState,
) -> AsyncMock:
    """Patch VZugApi constructor to return a pre-configured AsyncMock."""
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
        data={
            CONF_BASE_URL: "http://192.168.1.100",
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
        unique_id="fc:1b:ff:aa:bb:cc",
    )
