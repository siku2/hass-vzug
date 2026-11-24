from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components import vzug


def _entry(version, minor_version, data):
    return SimpleNamespace(
        entry_id="entry-1", version=version, minor_version=minor_version, data=data
    )


def _client():
    client = MagicMock()
    client.aggregate_meta = AsyncMock(
        return_value=SimpleNamespace(mac_address="FC1BFF089027")
    )
    client.get_device_status = AsyncMock(return_value={"Serial": "11041 002516"})
    client.aclose = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_migration_moves_unique_ids_to_the_mac_address():
    """Entries from before 2.2 used the serial number in the unique IDs."""
    hass = MagicMock()
    registry = MagicMock()
    entities = [
        SimpleNamespace(entity_id="sensor.a", unique_id="11041 002516-status"),
        SimpleNamespace(entity_id="sensor.b", unique_id="other-status"),
    ]
    client = _client()

    with (
        patch.object(vzug.api, "VZugApi", return_value=client) as api_cls,
        patch.object(vzug.er, "async_get", return_value=registry),
        patch.object(vzug.er, "async_entries_for_config_entry", return_value=entities),
    ):
        assert await vzug.async_migrate_entry(
            hass, _entry(1, 1, {"host": "192.168.1.10"})
        )

    assert str(api_cls.call_args.args[0]) == "http://192.168.1.10"
    registry.async_update_entity.assert_called_once_with(
        "sensor.a", new_unique_id="fc:1b:ff:08:90:27-status"
    )
    client.aclose.assert_awaited_once()
    assert hass.config_entries.async_update_entry.call_args.kwargs == {
        "data": {"base_url": "http://192.168.1.10"},
        "version": 2,
        "minor_version": 2,
    }


@pytest.mark.asyncio
async def test_migration_closes_the_client_when_the_appliance_fails():
    client = _client()
    client.aggregate_meta.side_effect = TimeoutError

    with (
        patch.object(vzug.api, "VZugApi", return_value=client),
        patch.object(vzug.er, "async_get"),
        patch.object(vzug.er, "async_entries_for_config_entry", return_value=[]),
        pytest.raises(TimeoutError),
    ):
        await vzug.async_migrate_entry(
            MagicMock(), _entry(2, 1, {"base_url": "http://192.168.1.10"})
        )

    client.aclose.assert_awaited_once()
