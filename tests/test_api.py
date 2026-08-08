import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from custom_components.vzug.api import VZugApi


@pytest.fixture
def vzug_api():
    """Create a VZugApi instance for testing."""
    return VZugApi(base_url="http://example.com")


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

    vzug_api = VZugApi(base_url="http://example.com")

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

@pytest.mark.asyncio
async def test_zh_mode_warmup_disables_itself(vzug_api):
    """Appliances which don't know 'getZHMode' get probed exactly once."""
    with (
        patch.object(vzug_api, "get_zh_mode", new_callable=AsyncMock) as zh_mode,
        patch.object(vzug_api, "get_device_status", new_callable=AsyncMock),
        patch.object(
            vzug_api, "get_last_push_notifications", new_callable=AsyncMock
        ) as notifications,
        patch.object(vzug_api, "get_eco_info", new_callable=AsyncMock) as eco_info,
    ):
        zh_mode.side_effect = ValueError("device returned an error response")
        notifications.return_value = []
        eco_info.return_value = {}

        state = await vzug_api.aggregate_state()
        assert state.zh_mode == -1
        assert vzug_api._zh_mode_warmup is False

        await vzug_api.aggregate_state()
        assert zh_mode.call_count == 1


@pytest.mark.asyncio
async def test_zh_mode_warmup_runs_before_the_state_poll(vzug_api):
    """The warm-up is only useful if it precedes the other commands."""
    calls: list[str] = []

    async def _zh_mode(**kwargs):
        calls.append("getZHMode")
        return 2

    async def _eco_info(**kwargs):
        calls.append("getEcoInfo")
        return {"energy": {"total": 615.7}}

    with (
        patch.object(vzug_api, "get_zh_mode", side_effect=_zh_mode),
        patch.object(vzug_api, "get_device_status", new_callable=AsyncMock),
        patch.object(
            vzug_api, "get_last_push_notifications", new_callable=AsyncMock
        ) as notifications,
        patch.object(vzug_api, "get_eco_info", side_effect=_eco_info),
    ):
        notifications.return_value = []

        state = await vzug_api.aggregate_state()

        assert state.zh_mode == 2
        assert calls == ["getZHMode", "getEcoInfo"]
