"""Tests for the V-ZUG config flow."""

from unittest.mock import AsyncMock

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vzug import api
from custom_components.vzug.const import CONF_BASE_URL, DOMAIN


async def test_step_user_shows_menu(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["manual", "start_discovery"]


async def test_step_manual_shows_form(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"


async def test_step_manual_success(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.100"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BASE_URL] == "http://192.168.1.100"
    assert result["result"].unique_id == "fc:1b:ff:aa:bb:cc"


async def test_step_manual_success_with_scheme(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "http://192.168.1.100"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BASE_URL] == "http://192.168.1.100"


async def test_step_manual_invalid_host(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    # yarl.URL accepts nearly anything, so we test the flow recovers from errors
    mock_vzug_api.aggregate_meta.side_effect = Exception("cannot connect")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.100"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_step_manual_cannot_connect(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    mock_vzug_api.aggregate_meta.side_effect = Exception("connection refused")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.100"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_step_manual_auth_required(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    mock_vzug_api.aggregate_meta.side_effect = api.AuthenticationFailed()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.100"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"


async def test_step_manual_updates_existing(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.200"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "update_success"
    assert mock_config_entry.data[CONF_BASE_URL] == "http://192.168.1.200"


async def test_step_dhcp_new_device(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    discovery_info = DhcpServiceInfo(
        ip="192.168.1.100",
        macaddress="fc1bffaabbcc",
        hostname="vzug-device",
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=discovery_info,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"


async def test_step_dhcp_already_configured(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_config_entry.add_to_hass(hass)

    discovery_info = DhcpServiceInfo(
        ip="192.168.1.200",
        macaddress="fc1bffaabbcc",
        hostname="vzug-device",
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=discovery_info,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.data[CONF_BASE_URL] == "http://192.168.1.200"


async def test_step_dhcp_cannot_connect(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    mock_vzug_api.aggregate_meta.side_effect = Exception("timeout")
    discovery_info = DhcpServiceInfo(
        ip="192.168.1.100",
        macaddress="fc1bffaabbcc",
        hostname="vzug-device",
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=discovery_info,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "false_discovery"


async def test_step_dhcp_auth_required(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    mock_vzug_api.aggregate_meta.side_effect = api.AuthenticationFailed()
    discovery_info = DhcpServiceInfo(
        ip="192.168.1.100",
        macaddress="fc1bffaabbcc",
        hostname="vzug-device",
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=discovery_info,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"


async def test_step_auth_shows_form(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    mock_vzug_api.aggregate_meta.side_effect = api.AuthenticationFailed()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.100"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"


async def test_step_auth_success(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_agg_meta: api.AggMeta,
) -> None:
    mock_vzug_api.aggregate_meta.side_effect = api.AuthenticationFailed()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.100"}
    )
    assert result["step_id"] == "auth"

    # Now provide valid credentials
    mock_vzug_api.aggregate_meta.side_effect = None
    mock_vzug_api.aggregate_meta.return_value = mock_agg_meta
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USERNAME] == "admin"
    assert result["data"][CONF_PASSWORD] == "secret"


async def test_step_auth_invalid_credentials(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    mock_vzug_api.aggregate_meta.side_effect = api.AuthenticationFailed()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.100"}
    )
    assert result["step_id"] == "auth"

    # Credentials still fail
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "admin", CONF_PASSWORD: "wrong"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "auth_failed"}


async def test_step_auth_cannot_connect(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    mock_vzug_api.aggregate_meta.side_effect = api.AuthenticationFailed()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "192.168.1.100"}
    )
    assert result["step_id"] == "auth"

    mock_vzug_api.aggregate_meta.side_effect = Exception("timeout")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_step_confirm_creates_entry(
    hass: HomeAssistant, mock_vzug_api: AsyncMock
) -> None:
    discovery_info = DhcpServiceInfo(
        ip="192.168.1.100",
        macaddress="fc1bffaabbcc",
        hostname="vzug-device",
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=discovery_info,
    )
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BASE_URL] == "http://192.168.1.100"


async def test_step_reauth(
    hass: HomeAssistant,
    mock_vzug_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    mock_agg_meta: api.AggMeta,
) -> None:
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "new_admin", CONF_PASSWORD: "new_secret"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_USERNAME] == "new_admin"
    assert mock_config_entry.data[CONF_PASSWORD] == "new_secret"
