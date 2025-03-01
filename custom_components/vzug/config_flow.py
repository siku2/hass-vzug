"""Config flow for V-ZUG integration."""

import asyncio
import logging
from collections.abc import Iterator
from ipaddress import IPv4Interface
from typing import Any, cast

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.dhcp import DhcpServiceInfo
from homeassistant.components.network import Adapter, async_get_adapters
from homeassistant.const import CONF_BASE, CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import discovery_flow as df
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from yarl import URL

from . import api
from .const import CONF_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

_DISCOVERY_TIMEOUT = 3.0

ABORT_UPDATE_SUCCESS = "update_success"
ABORT_FALSE_DISCOVERY = "false_discovery"
ABORT_DISCOVERY_FINISHED = "discovery_finished"

ERR_AUTH_FAILED = "auth_failed"
ERR_INVALID_HOST = "invalid_host"
ERR_CANNOT_CONNECT = "cannot_connect"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for V-ZUG."""

    VERSION = 2
    MINOR_VERSION = 2

    def __init__(self) -> None:
        self._base_url: URL | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._client: api.VZugApi | None = None
        self._meta: api.AggMeta | None = None

    def _set_client(self) -> None:
        assert self._base_url
        if self._username is not None and self._password is not None:
            credentials = api.Credentials(
                username=self._username, password=self._password
            )
        else:
            credentials = None

        self._client = api.VZugApi(
            self._base_url,
            credentials=credentials,
        )

    # entry points

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self.async_show_menu(
            step_id="user", menu_options=["manual", "start_discovery"]
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                base_url = URL(user_input["host"])
                if not base_url.is_absolute():
                    base_url = URL(f"http://{base_url}")
            except Exception:
                errors[CONF_HOST] = ERR_INVALID_HOST
            else:
                self._base_url = base_url
                if res := await self._check_device(
                    needs_confirmation=False, errors=errors
                ):
                    return res

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        self._base_url = URL(entry_data[CONF_BASE_URL])
        self._username = entry_data.get(CONF_USERNAME)

        return await self.async_step_auth()

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> FlowResult:
        _LOGGER.debug("dhcp discovery: %s", discovery_info)
        self._base_url = URL(f"http://{discovery_info.ip}")

        await self.async_set_unique_id(dr.format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(
            updates={CONF_BASE_URL: str(self._base_url)}
        )

        if res := await self._check_device(needs_confirmation=True, errors={}):
            return res
        return self.async_abort(reason=ABORT_FALSE_DISCOVERY)

    async def async_step_start_discovery(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        adapters = await async_get_adapters(self.hass)
        results = await asyncio.gather(
            *(
                api.discovery.discover_list(interface, timeout=_DISCOVERY_TIMEOUT)
                for interface in _iter_adapter_interfaces(adapters)
            ),
            return_exceptions=True,
        )
        discoveries: set[api.discovery.DiscoveryInfo] = {
            d for group in results if not isinstance(group, Exception) for d in group
        }
        for discovery in discoveries:
            df.async_create_flow(
                self.hass,
                DOMAIN,
                {"source": config_entries.SOURCE_DISCOVERY},
                discovery,
            )
        return self.async_abort(
            reason=ABORT_DISCOVERY_FINISHED,
            description_placeholders={"count": str(len(discoveries))},
        )

    async def async_step_discovery(self, discovery_info: Any) -> FlowResult:
        discovery_info = cast(api.discovery.DiscoveryInfo, discovery_info)
        _LOGGER.debug("setting up manually discovered device: %s", discovery_info)
        self._base_url = URL(f"http://{discovery_info.host}")

        if res := await self._check_device(needs_confirmation=True, errors={}):
            return res
        return self.async_abort(reason=ABORT_FALSE_DISCOVERY)

    async def _check_device(
        self, *, needs_confirmation: bool, errors: dict[str, str]
    ) -> FlowResult | None:
        self._set_client()
        assert self._client

        try:
            self._meta = await self._client.aggregate_meta()
        except api.AuthenticationFailed:
            return await self.async_step_auth()
        except Exception:
            errors[CONF_BASE] = ERR_CANNOT_CONNECT
            return None

        if needs_confirmation:
            return await self.async_step_confirm()
        return await self._create_entry()

    # authentication

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            self._set_client()
            assert self._client
            try:
                self._meta = await self._client.aggregate_meta()
            except api.AuthenticationFailed:
                errors[CONF_BASE] = ERR_AUTH_FAILED
            except Exception:
                errors[CONF_BASE] = ERR_CANNOT_CONNECT
            else:
                return await self._create_entry()

        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=self._username): TextSelector(
                        TextSelectorConfig(autocomplete="username")
                    ),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.PASSWORD,
                            autocomplete="current-password",
                        )
                    ),
                }
            ),
            errors=errors,
        )

    # end

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return await self._create_entry()

        return self.async_show_form(step_id="confirm")

    async def _create_entry(self) -> FlowResult:
        assert self._base_url
        assert self._meta

        data = {
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_BASE_URL: str(self._base_url),
        }
        existing_entry = await self.async_set_unique_id(
            dr.format_mac(self._meta.mac_address)
        )
        if existing_entry:
            _LOGGER.debug("updating existing entry")
            self.hass.config_entries.async_update_entry(existing_entry, data=data)
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(existing_entry.entry_id)
            )

            return self.async_abort(reason=ABORT_UPDATE_SUCCESS)

        _LOGGER.debug("creating entry")
        return self.async_create_entry(title=self._meta.create_unique_name(), data=data)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


def _iter_adapter_interfaces(adapters: list[Adapter]) -> Iterator[IPv4Interface]:
    for adapter in adapters:
        if not adapter["enabled"]:
            continue
        for ip_info in adapter["ipv4"]:
            yield IPv4Interface(f"{ip_info['address']}/{ip_info['network_prefix']}")
