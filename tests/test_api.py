import httpx
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from custom_components.vzug.api import VZugApi


def _create_test_client() -> httpx.AsyncClient:
    """Create an httpx client for testing."""
    transport = httpx.AsyncHTTPTransport(
        verify=False,
        limits=httpx.Limits(max_connections=3, max_keepalive_connections=1),
        retries=5,
    )
    return httpx.AsyncClient(transport=transport)


@pytest.fixture
def vzug_api():
    """Create a VZugApi instance for testing."""
    return VZugApi(base_url="http://example.com", client=_create_test_client())


@pytest.mark.asyncio
async def test_get_eco_info_with_data(vzug_api):
    """Test get_eco_info with normal data response."""
    # Mock response data
    mock_response = {
        "water": {"total": 42.5, "average": 6.7, "program": 8.9},
        "energy": {"total": 90.4, "average": 0.5, "program": 0.5},
    }

    # Patch the _command method to return our mock data
    with patch.object(vzug_api, "_command", new_callable=AsyncMock) as mock_command:
        mock_command.return_value = mock_response

        # Call the method under test
        result = await vzug_api.get_eco_info()

        # Verify the command was called correctly
        mock_command.assert_called_once_with(
            "hh", command="getEcoInfo", expected_type=dict, value_on_err=None
        )

        # Verify the result is as expected
        assert result == mock_response
        assert result["water"]["total"] == 42.5
        assert result["energy"]["total"] == 90.4


@pytest.mark.asyncio
async def test_get_eco_info_returns_none_when_zeros(vzug_api):
    """Test get_eco_info returns None when water and energy totals are both 0."""
    # Mock response with zeros
    mock_response = {
        "water": {"total": 0, "average": 0, "program": 0},
        "energy": {"total": 0, "average": 0, "program": 0},
    }

    # Patch the _command method to return our mock data
    with patch.object(vzug_api, "_command", new_callable=AsyncMock) as mock_command:
        mock_command.return_value = mock_response

        # Call the method under test
        result = await vzug_api.get_eco_info()

        # Verify result is an empty dictionary
        assert result == {}


@pytest.mark.asyncio
async def test_get_eco_info_incomplete_data(vzug_api):
    """Test get_eco_info with incomplete data."""
    # Mock response with missing fields
    mock_response = {"energy": {"average": 0.5, "program": 0.5}}

    # Patch the _command method to return our mock data
    with patch.object(vzug_api, "_command", new_callable=AsyncMock) as mock_command:
        mock_command.return_value = mock_response

        # Call the method under test
        result = await vzug_api.get_eco_info()

        # Should use default value of -1 when total is missing
        assert result == {}


@pytest.mark.asyncio
async def test_get_eco_info_with_door_openings(vzug_api):
    """Test get_eco_info with door openings data (refrigerator)."""
    mock_response = {
        "doorOpenings": {
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
    }

    with patch.object(vzug_api, "_command", new_callable=AsyncMock) as mock_command:
        mock_command.return_value = mock_response

        result = await vzug_api.get_eco_info()

        # Should NOT be discarded even though water/energy totals are 0
        assert "doorOpenings" in result
        assert result["doorOpenings"]["door0"]["today"]["amount"] == 20


@pytest.mark.asyncio
async def test_aggregate_program_filters_zones(vzug_api):
    """Test aggregate_program only returns items with 'zone' key."""
    mock_response = [
        {"id": 2000, "status": "active", "temp": {"set": 5.0, "act": 5.0}, "doorClosed": True, "zone": "fridge1"},
        {"id": 2001, "status": "active", "temp": {"set": -18.0, "act": -18.0}, "doorClosed": True, "zone": "freezer1"},
        {"status": "idle", "duration": {"min": 0, "max": 35700}, "zone": "countdown1"},
    ]

    with patch.object(vzug_api, "_command", new_callable=AsyncMock) as mock_command:
        mock_command.return_value = mock_response

        result = await vzug_api.aggregate_program()

        assert len(result.zones) == 3
        assert result.zones[0]["zone"] == "fridge1"
        assert result.zones[1]["zone"] == "freezer1"


@pytest.mark.asyncio
async def test_supports_update_status_uses_ai_version():
    """Test supports_update_status uses AI API version, not HH."""
    from custom_components.vzug.api import AggMeta

    # KS case: HH=1.6.0, AI=1.8.0 → should support updates
    meta_ks = AggMeta(
        mac_address="AA:BB:CC:DD:EE:FF",
        model_id="CCO4T",
        model_name="CombiCooler V4000",
        device_name="Refrigerator",
        serial_number="51108 116207",
        api_version=(1, 6, 0),
        ai_api_version=(1, 8, 0),
    )
    assert meta_ks.supports_update_status() is True

    # Old device: HH=1.5.0, AI=1.5.0 → should not support updates
    meta_old = AggMeta(
        mac_address="AA:BB:CC:DD:EE:FF",
        model_id="OLD",
        model_name="Old Device",
        device_name="Old",
        serial_number="00000 000000",
        api_version=(1, 5, 0),
        ai_api_version=(1, 5, 0),
    )
    assert meta_old.supports_update_status() is False


@pytest.mark.asyncio
async def test_get_hh_device_status(vzug_api):
    """Test get_hh_device_status returns device status."""
    mock_response = {
        "errors": [{"displayCode": "E01"}],
        "displayedErrors": [],
        "notifications": [],
        "isUpdatePossible": True,
    }

    with patch.object(vzug_api, "_command", new_callable=AsyncMock) as mock_command:
        mock_command.return_value = mock_response
        result = await vzug_api.get_hh_device_status()

        mock_command.assert_called_once_with(
            "hh", command="getDeviceStatus", expected_type=dict, value_on_err=None
        )
        assert len(result["errors"]) == 1
        assert result["isUpdatePossible"] is True


@pytest.mark.asyncio
async def test_get_cloud_status(vzug_api):
    """Test get_cloud_status returns cloud status."""
    mock_response = {
        "enabled": True,
        "claimed": True,
        "status": "connected",
        "secTokenValid": True,
    }

    with patch.object(vzug_api, "_command", new_callable=AsyncMock) as mock_command:
        mock_command.return_value = mock_response
        result = await vzug_api.get_cloud_status()

        mock_command.assert_called_once_with(
            "ai", command="getCloudStatus", expected_type=dict, value_on_err=None
        )
        assert result["status"] == "connected"


@pytest.mark.asyncio
async def test_get_program_list_with_names(vzug_api):
    """Test get_program_list resolves names from getProgram responses."""
    with patch.object(vzug_api, "get_all_program_ids", new_callable=AsyncMock) as mock_ids:
        mock_ids.return_value = [50, 51]

        with patch.object(vzug_api, "get_program_by_id", new_callable=AsyncMock) as mock_prog:
            mock_prog.side_effect = [
                [{"id": 50, "name": "Normal", "status": "idle"}],
                [{"id": 51, "name": "Eco", "status": "idle"}],
            ]

            result = await vzug_api.get_program_list()

            assert result == {50: "Normal", 51: "Eco"}


@pytest.mark.asyncio
async def test_get_program_list_without_names(vzug_api):
    """Test get_program_list falls back to str(id) when no name."""
    with patch.object(vzug_api, "get_all_program_ids", new_callable=AsyncMock) as mock_ids:
        mock_ids.return_value = [50, 51]

        with patch.object(vzug_api, "get_program_by_id", new_callable=AsyncMock) as mock_prog:
            mock_prog.side_effect = [
                [{"id": 50, "status": "idle"}],
                [{"id": 51, "status": "idle"}],
            ]

            result = await vzug_api.get_program_list()

            assert result == {50: "50", 51: "51"}


@pytest.mark.asyncio
async def test_get_program_list_filters_zone_programs(vzug_api):
    """Test get_program_list filters out zone programs (KS fridge/freezer)."""
    with patch.object(vzug_api, "get_all_program_ids", new_callable=AsyncMock) as mock_ids:
        mock_ids.return_value = [2000, 2001, 9000]

        with patch.object(vzug_api, "get_program_by_id", new_callable=AsyncMock) as mock_prog:
            mock_prog.side_effect = [
                [{"id": 2000, "zone": "fridge1", "status": "active"}],
                [{"id": 2001, "zone": "freezer1", "status": "active"}],
                [{"id": 9000, "name": "Special", "status": "idle"}],
            ]

            result = await vzug_api.get_program_list()

            # Zone programs should be filtered out
            assert 2000 not in result
            assert 2001 not in result
            assert result == {9000: "Special"}


@pytest.mark.asyncio
async def test_json_repair_with_valid_json(vzug_api):
    """Test that valid JSON is processed normally without repair."""
    valid_json = '{"status": "idle", "value": 123}'

    # Mock httpx response properly
    mock_response = MagicMock()
    mock_response.json.return_value = valid_json
    mock_response.raise_for_status.return_value = None

    with patch.object(vzug_api._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await vzug_api._command("ai", command="getDeviceStatus")

        assert result == valid_json
        mock_response.json.assert_called_once()


@pytest.mark.asyncio
async def test_json_repair_with_real_broken_device_status():
    """Test JSON repair with a realistic broken device status response."""
    # Example of broken JSON that might come from V-ZUG device
    broken_json = """[{"date":"2025-06-10T16:06:06Z","message":"Der Betrieb wurde beendet."}\n,{"date":"2025-06-10T15:40:43Z","message":"Das Vorheizen wurde beendet. Bitte schieben Sie das Gargut ein."} ,{"date":"2025-06-04T16:38:18Z","message":"Aufgeheizt"} ,{"date":"2025-06-04T09:50:01Z","message":"Aufgeheizt"} ,{"date":"2025-06-04T09:40:01Z","message":"Betriebsart gestartet"} ,{"date":"2025-05-26T16:07:52Z","message":"Aufgeheizt"} ,{"date":"2025-05-25T09:37:41Z","message":"Das Vorheizen wurde beendet. Bitte schieben Sie das Gargut ein."} ,{"date":"2025-05-21T10:24:55Z","message"]"""

    vzug_api = VZugApi(base_url="http://example.com", client=_create_test_client())

    # Mock httpx response that fails json() but has content
    mock_response = MagicMock()
    mock_response.json.side_effect = ValueError(
        "Expecting property name enclosed in double quotes"
    )
    mock_response.content = broken_json.encode()
    mock_response.text = broken_json
    mock_response.raise_for_status.return_value = None

    with patch.object(vzug_api._client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        # This will use the REAL json_repair library
        result = await vzug_api._command("hh", command="getProgram")

        assert result is not None
        assert len(result) == 8
