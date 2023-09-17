"""Config flow for V-ZUG integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.dhcp import DhcpServiceInfo
from homeassistant.const import CONF_BASE, CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from yarl import URL

from . import api
from .const import CONF_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

ABORT_UPDATE_SUCCESS = "update_success"

ERR_AUTH_FAILED = "auth_failed"
ERR_INVALID_HOST = "invalid_host"
ERR_CANNOT_CONNECT = "cannot_connect"


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for V-ZUG."""

    VERSION = 2

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
        errors: dict[str, str] = {}
        if user_input:
            try:
                base_url = URL(user_input["host"])
                if not base_url.is_absolute():
                    base_url = URL(f"http://{base_url}")
            except Exception:
                errors[CONF_HOST] = ERR_INVALID_HOST
            else:
                self._base_url = base_url
                self._set_client()
                assert self._client
                try:
                    self._meta = await self._client.aggregate_meta()
                except api.AuthenticationFailed:
                    return await self.async_step_auth()
                except Exception:
                    errors[CONF_BASE] = ERR_CANNOT_CONNECT
                else:
                    return await self._create_entry()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        self._base_url = URL(entry_data[CONF_BASE_URL])
        self._username = entry_data.get(CONF_USERNAME)

        return await self.async_step_auth()

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> FlowResult:
        return await super().async_step_dhcp(discovery_info)

    # authentication

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input:
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

    async def _create_entry(self) -> FlowResult:
        assert self._base_url
        assert self._meta

        data = {
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_BASE_URL: str(self._base_url),
        }
        existing_entry = await self.async_set_unique_id(self._meta.mac_address)
        if existing_entry:
            self.hass.config_entries.async_update_entry(existing_entry, data=data)
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(existing_entry.entry_id)
            )

            return self.async_abort(reason=ABORT_UPDATE_SUCCESS)

        return self.async_create_entry(title=self._meta.create_unique_name(), data=data)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
