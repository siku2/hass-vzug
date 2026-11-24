"""Bluetooth discovery of an appliance that is already set up."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.vzug.api import provisioning
from custom_components.vzug.config_flow import ConfigFlow
from custom_components.vzug.const import DOMAIN

SERIAL = "21057 000246"
BLE_ADDRESS = "FC:1B:FF:08:90:27"


def _discovery():
    return SimpleNamespace(
        address=BLE_ADDRESS,
        manufacturer_data={provisioning.MANUFACTURER_ID: SERIAL.encode()},
    )


def _flow():
    flow = ConfigFlow()
    flow.hass = MagicMock()
    flow.context = {}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


@pytest.mark.asyncio
async def test_bluetooth_address_is_added_to_the_configured_appliance():
    """The appliance shows up once, with its Bluetooth address as a connection."""
    device = SimpleNamespace(id="device-1", connections=set())
    registry = MagicMock()
    registry.async_get_device.return_value = device

    with patch.object(dr, "async_get", return_value=registry):
        result = await _flow().async_step_bluetooth(_discovery())

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    registry.async_get_device.assert_called_once_with(identifiers={(DOMAIN, SERIAL)})
    registry.async_update_device.assert_called_once_with(
        "device-1",
        merge_connections={(dr.CONNECTION_BLUETOOTH, "fc:1b:ff:08:90:27")},
    )


@pytest.mark.asyncio
async def test_known_bluetooth_address_is_left_alone():
    device = SimpleNamespace(
        id="device-1",
        connections={(dr.CONNECTION_BLUETOOTH, "fc:1b:ff:08:90:27")},
    )
    registry = MagicMock()
    registry.async_get_device.return_value = device

    with patch.object(dr, "async_get", return_value=registry):
        result = await _flow().async_step_bluetooth(_discovery())

    assert result["reason"] == "already_configured"
    registry.async_update_device.assert_not_called()


@pytest.mark.asyncio
async def test_bluetooth_address_of_another_device_still_aborts():
    """If another device already has the address, the discovery still ends."""
    device = SimpleNamespace(id="device-1", connections=set())
    registry = MagicMock()
    registry.async_get_device.return_value = device
    registry.async_update_device.side_effect = dr.DeviceConnectionCollisionError(
        {(dr.CONNECTION_BLUETOOTH, "fc:1b:ff:08:90:27")}, MagicMock()
    )

    with patch.object(dr, "async_get", return_value=registry):
        result = await _flow().async_step_bluetooth(_discovery())

    assert result["reason"] == "already_configured"
