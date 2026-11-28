"""The config flow in a running Home Assistant, against simulated appliances."""

import sys
from ipaddress import IPv4Interface
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from custom_components.vzug import api, config_flow
from custom_components.vzug import async_setup_entry as real_async_setup_entry
from custom_components.vzug.api import provisioning
from custom_components.vzug.const import CONF_BASE_URL, DOMAIN

from .appliance import ApplianceNetwork, FakeAppliance
from .common import mock_entry, setup_appliance

DEVICE = "adora_dish_v6000"
SERIAL = "46126 182263"


@pytest.fixture(autouse=True)
def _no_setup():
    """The flow is tested on its own, the entry it creates isn't set up."""
    with patch("custom_components.vzug.async_setup_entry", return_value=True) as mock:
        yield mock


async def _start_manual(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["manual", "start_discovery"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    return result


def _assert_entry(result: dict, appliance: FakeAppliance, **data) -> None:
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    assert result["title"] == "Adora SL (46126 182263)"
    assert result["data"] == {
        CONF_USERNAME: None,
        CONF_PASSWORD: None,
        CONF_BASE_URL: appliance.base_url,
        **data,
    }
    assert result["result"].unique_id == dr.format_mac(appliance.mac_address)


# manual


@pytest.mark.parametrize(
    "host", ["adora-dish-v6000.local", "http://adora-dish-v6000.local"]
)
async def test_manual(
    hass: HomeAssistant, appliances: ApplianceNetwork, host: str
) -> None:
    appliance = appliances.add(DEVICE)
    result = await _start_manual(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host}
    )
    _assert_entry(result, appliance)


async def test_manual_https(hass: HomeAssistant, appliances: ApplianceNetwork) -> None:
    appliances.add(DEVICE)
    result = await _start_manual(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "https://adora-dish-v6000.local"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BASE_URL] == "https://adora-dish-v6000.local"


@pytest.mark.parametrize("host", ["http://[::1", "http://", "  "])
async def test_manual_invalid_host(
    hass: HomeAssistant, appliances: ApplianceNetwork, host: str
) -> None:
    result = await _start_manual(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: host}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "invalid_host"}


async def test_manual_cannot_connect_then_recovers(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE)
    appliance.reachable = False
    result = await _start_manual(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: appliance.host}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    appliance.reachable = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: appliance.host}
    )
    _assert_entry(result, appliance)


async def test_manual_already_configured_updates_address(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE)
    entry = mock_entry(appliance, **{CONF_BASE_URL: "http://192.0.2.1"})
    entry.add_to_hass(hass)

    result = await _start_manual(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: appliance.host}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_BASE_URL] == appliance.base_url
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


# authentication


async def test_password_protected_appliance(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE, username="admin", password="secret")
    result = await _start_manual(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: appliance.host}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "auth_failed"}

    appliance.reachable = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    appliance.reachable = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}
    )
    _assert_entry(
        result, appliance, **{CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}
    )


async def test_reauth(hass: HomeAssistant, appliances: ApplianceNetwork) -> None:
    appliance = appliances.add(DEVICE, username="admin", password="secret")
    entry = mock_entry(appliance, **{CONF_PASSWORD: "old"})
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"] == {"name": entry.title}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "auth_failed"}

    appliance.reachable = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    appliance.reachable = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_USERNAME] == "admin"
    assert entry.data[CONF_PASSWORD] == "secret"
    assert entry.data[CONF_BASE_URL] == appliance.base_url


async def test_reauth_with_another_appliance(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    """The address now leads to another appliance, its credentials don't belong."""
    appliance = appliances.add(DEVICE, username="admin", password="secret")
    entry = mock_entry(appliance, **{CONF_PASSWORD: "old"})
    entry.add_to_hass(hass)
    # the other appliance took over the address
    other = appliances.add(
        "adora_wash_v6000", host=appliance.host, username="admin", password="secret"
    )
    assert appliances.appliances[appliance.host] is other

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_PASSWORD] == "old"


# DHCP


def _dhcp(appliance: FakeAppliance) -> DhcpServiceInfo:
    return DhcpServiceInfo(
        ip=appliance.host,
        hostname="vzug",
        macaddress=appliance.mac_address.replace(":", ""),
    )


async def test_dhcp(hass: HomeAssistant, appliances: ApplianceNetwork) -> None:
    appliance = appliances.add(DEVICE)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp(appliance)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    _assert_entry(result, appliance)


async def test_dhcp_updates_address_of_configured_appliance(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE)
    entry = mock_entry(appliance, **{CONF_BASE_URL: "http://192.0.2.1"})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp(appliance)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_BASE_URL] == appliance.base_url


async def test_dhcp_not_an_appliance(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE)
    appliance.reachable = False
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp(appliance)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "false_discovery"


async def test_dhcp_password_protected(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE, username="admin", password="secret")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp(appliance)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"


# network discovery


async def test_start_discovery(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE)
    adapters = [
        {"enabled": True, "ipv4": [{"address": "192.0.2.10", "network_prefix": 24}]},
        {
            "enabled": False,
            "ipv4": [{"address": "198.51.100.10", "network_prefix": 24}],
        },
    ]
    found = [api.discovery.DiscoveryInfo(host=appliance.host)]
    with (
        patch.object(config_flow, "async_get_adapters", return_value=adapters),
        patch.object(
            api.discovery, "discover_list", AsyncMock(return_value=found)
        ) as discover,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "start_discovery"}
        )
        await hass.async_block_till_done(wait_background_tasks=True)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "discovery_finished"
    assert result["description_placeholders"] == {"count": "1"}
    discover.assert_awaited_once_with(
        IPv4Interface("192.0.2.10/24"), timeout=config_flow._DISCOVERY_TIMEOUT
    )

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["step_id"] == "confirm"
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {})
    _assert_entry(result, appliance)


async def test_discovery_of_configured_appliance_updates_address(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE)
    entry = mock_entry(appliance, **{CONF_BASE_URL: "http://192.0.2.1"})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DISCOVERY},
        data=api.discovery.DiscoveryInfo(host=appliance.host),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_BASE_URL] == appliance.base_url


async def test_discovery_not_an_appliance(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DISCOVERY},
        data=api.discovery.DiscoveryInfo(host="192.0.2.99"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "false_discovery"


# Bluetooth


def _ble(serial: bytes = SERIAL.encode()) -> SimpleNamespace:
    return SimpleNamespace(
        address="FC:1B:FF:08:90:27",
        manufacturer_data={provisioning.MANUFACTURER_ID: serial},
    )


async def _start_bluetooth(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=_ble()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "wifi"
    assert result["description_placeholders"] == {"serial": SERIAL}
    return result


async def test_bluetooth_provisioning(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE)
    result = await _start_bluetooth(hass)
    with patch.object(
        config_flow.ConfigFlow, "_provision", AsyncMock(return_value=appliance.host)
    ) as provision:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"ssid": "home", CONF_PASSWORD: "wifi-secret"}
        )
    provision.assert_awaited_once_with("home", "wifi-secret")
    _assert_entry(result, appliance)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (provisioning.WrongCredentials("wrong"), "wifi_credentials"),
        (provisioning.ProvisioningError("out of range"), "bluetooth_failed"),
    ],
)
async def test_bluetooth_provisioning_fails(
    hass: HomeAssistant, appliances: ApplianceNetwork, error: Exception, expected: str
) -> None:
    result = await _start_bluetooth(hass)
    with patch.object(
        config_flow.ConfigFlow, "_provision", AsyncMock(side_effect=error)
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"ssid": "home", CONF_PASSWORD: "wifi-secret"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_bluetooth_without_bluetooth_integration(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    result = await _start_bluetooth(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ssid": "home", CONF_PASSWORD: "wifi-secret"}
    )
    assert result["errors"] == {"base": "bluetooth_failed"}


async def test_bluetooth_not_an_appliance(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=_ble(b"\xff\xfe"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "false_discovery"


async def test_bluetooth_configured_appliance_gets_its_address(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    """The appliance shows up once, with its Bluetooth address as a connection."""
    appliance = appliances.add(DEVICE)
    with patch("custom_components.vzug.async_setup_entry", real_async_setup_entry):
        await setup_appliance(hass, appliance)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=_ble()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    [device] = dr.async_get(hass).async_get_devices(identifiers={(DOMAIN, SERIAL)})
    assert (dr.CONNECTION_BLUETOOTH, "fc:1b:ff:08:90:27") in device.connections


@pytest.fixture
def bluetooth(hass: HomeAssistant):
    """Home Assistant's Bluetooth integration, with one appliance in range."""
    hass.config.components.add("bluetooth")
    module = SimpleNamespace(async_ble_device_from_address=MagicMock())
    with patch.dict(sys.modules, {"homeassistant.components.bluetooth": module}):
        yield module


async def test_bluetooth_provisions_over_ble(
    hass: HomeAssistant, appliances: ApplianceNetwork, bluetooth
) -> None:
    appliance = appliances.add(DEVICE)
    client = MagicMock(disconnect=AsyncMock())
    result = await _start_bluetooth(hass)
    with (
        patch(
            "bleak_retry_connector.establish_connection",
            AsyncMock(return_value=client),
        ) as connect,
        patch.object(
            provisioning, "provision", AsyncMock(return_value=appliance.host)
        ) as provision,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"ssid": "home", CONF_PASSWORD: "wifi-secret"}
        )
    _assert_entry(result, appliance)
    bluetooth.async_ble_device_from_address.assert_called_once_with(
        hass, "FC:1B:FF:08:90:27", connectable=True
    )
    assert connect.await_args.args[2] == SERIAL
    provision.assert_awaited_once_with(client, "home", "wifi-secret")
    client.disconnect.assert_awaited_once()


async def test_bluetooth_out_of_range(
    hass: HomeAssistant, appliances: ApplianceNetwork, bluetooth
) -> None:
    bluetooth.async_ble_device_from_address.return_value = None
    result = await _start_bluetooth(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"ssid": "home", CONF_PASSWORD: "wifi-secret"}
    )
    assert result["errors"] == {"base": "bluetooth_failed"}


async def test_reconfigure(hass: HomeAssistant, appliances: ApplianceNetwork) -> None:
    appliance = appliances.add(DEVICE, username="admin", password="secret")
    entry = mock_entry(appliance, **{CONF_BASE_URL: "http://192.0.2.1"})
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    schema = result["data_schema"].schema
    assert next(iter(schema)).description == {"suggested_value": "192.0.2.1"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "http://[::1"}
    )
    assert result["errors"] == {CONF_HOST: "invalid_host"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.0.2.99"}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: appliance.host}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_BASE_URL] == appliance.base_url
    assert entry.data[CONF_PASSWORD] == "secret"


async def test_reconfigure_to_another_appliance(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE)
    other = appliances.add("adora_wash_v6000")
    entry = mock_entry(appliance)
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: other.host}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert entry.data[CONF_BASE_URL] == appliance.base_url


async def test_reconfigure_with_changed_credentials(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE, username="admin", password="secret")
    entry = mock_entry(appliance, **{CONF_PASSWORD: "old"})
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: appliance.host}
    )
    assert result["errors"] == {"base": "auth_failed"}


async def test_reconfigure_shows_a_full_url(
    hass: HomeAssistant, appliances: ApplianceNetwork
) -> None:
    appliance = appliances.add(DEVICE)
    entry = mock_entry(appliance, **{CONF_BASE_URL: "https://192.0.2.1"})
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    schema = result["data_schema"].schema
    assert next(iter(schema)).description == {"suggested_value": "https://192.0.2.1"}
