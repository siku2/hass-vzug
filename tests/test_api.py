import pytest
from unittest.mock import patch, AsyncMock

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
        "water": {
            "total": 42.5,
            "average": 6.7,
            "program": 8.9
        },
        "energy": {
            "total": 90.4,
            "average": 0.5,
            "program": 0.5
        }
    }

    # Patch the _command method to return our mock data
    with patch.object(vzug_api, '_command', new_callable=AsyncMock) as mock_command:
        mock_command.return_value = mock_response

        # Call the method under test
        result = await vzug_api.get_eco_info()

        # Verify the command was called correctly
        mock_command.assert_called_once_with(
            "hh",
            command="getEcoInfo",
            expected_type=dict,
            value_on_err=None
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
        "water": {
            "total": 0,
            "average": 0,
            "program": 0
        },
        "energy": {
            "total": 0,
            "average": 0,
            "program": 0
        }
    }

    # Patch the _command method to return our mock data
    with patch.object(vzug_api, '_command', new_callable=AsyncMock) as mock_command:
        mock_command.return_value = mock_response

        # Call the method under test
        result = await vzug_api.get_eco_info()

        # Verify result is None as specified in the function
        assert result is None


@pytest.mark.asyncio
async def test_get_eco_info_incomplete_data(vzug_api):
    """Test get_eco_info with incomplete data."""
    # Mock response with missing fields
    mock_response = {
        "energy": {
            "average": 0.5,
            "program": 0.5
        }
    }

    # Patch the _command method to return our mock data
    with patch.object(vzug_api, '_command', new_callable=AsyncMock) as mock_command:
        mock_command.return_value = mock_response

        # Call the method under test
        result = await vzug_api.get_eco_info()

        # Should use default value of -1 when total is missing
        assert result == mock_response
