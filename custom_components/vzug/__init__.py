"""The V-ZUG integration."""

import dataclasses
import enum
import logging
import typing
from collections.abc import Awaitable
from datetime import timedelta

import yarl
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import api
from .const import DOMAIN
from .helpers import get_device_name

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.UPDATE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up V-ZUG from a config entry."""
    base_url = yarl.URL(entry.data["host"])
    coordinator = Coordinator(hass, base_url)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


@dataclasses.dataclass(kw_only=True)
class Data:
    device: api.DeviceStatus | None
    update: api.UpdateStatus | None
    ai_fw_version: api.AiFwVersion | None
    hh_fw_version: api.HhFwVersion | None
    notifications: list[api.PushNotification]


class DeviceCategory(enum.StrEnum):
    ADORA_DISH = enum.auto()
    ADORA_WASH = enum.auto()

    @classmethod
    def from_model_description(cls, desc: str):
        desc = desc.lower()
        if "adorawash" in desc:
            return cls.ADORA_WASH
        if "adoradish" in desc:
            return cls.ADORA_DISH
        return None


class Coordinator(DataUpdateCoordinator[Data]):
    api: "api.VZugApi"
    device_info: DeviceInfo
    unique_id_prefix: str
    category: DeviceCategory | None

    def __init__(
        self,
        hass: HomeAssistant,
        base_url: yarl.URL,
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=30)
        )

        self.api = api.VZugApi(async_get_clientsession(hass), base_url)
        self.device_info = DeviceInfo(manufacturer="V-ZUG")
        self.unique_id_prefix = ""
        self.category = None

        self._mac_addr: str | None = None
        self._model_description: str | None = None

    async def _async_update_data(self) -> Data:
        try:
            device = await self.api.get_device_status()
        except Exception as exc:
            raise UpdateFailed(f"device status: {exc}") from exc

        update = await _wait_or_none(self.api.get_update_status(), msg="update status")
        ai_fw_version = await _wait_or_none(
            self.api.get_ai_fw_version(), msg="AI FW Version"
        )
        hh_fw_version = await _wait_or_none(
            self.api.get_hh_fw_version(), msg="HH FW Version"
        )
        notifications = await _wait_or_none(
            self.api.get_last_push_notifications(), msg="push notifications"
        )
        if not notifications:
            notifications = []

        if self._mac_addr is None:
            self._mac_addr = await _wait_or_none(
                self.api.get_mac_address(), msg="MAC address"
            )
        if self._model_description is None:
            self._model_description = await _wait_or_none(
                self.api.get_model_description(), msg="model description"
            )

        if self.category is None and self._model_description is not None:
            self.category = DeviceCategory.from_model_description(
                self._model_description
            )

        if self.unique_id_prefix == "":
            self.unique_id_prefix = device["deviceUuid"]

        # Update device info

        self.device_info["configuration_url"] = str(self.api.base_url)
        self.device_info.setdefault("identifiers", set()).add(
            (DOMAIN, device["Serial"])
        )

        if not self.device_info.get("name"):
            self.device_info["name"] = get_device_name(device, self._model_description)

        if ai_fw_version is not None:
            self.device_info["hw_version"] = ai_fw_version.get("HW")
            self.device_info["sw_version"] = ai_fw_version.get("SW")

        if mac_addr := self._mac_addr:
            self.device_info.setdefault("connections", set()).add(
                (device_registry.CONNECTION_NETWORK_MAC, mac_addr)
            )
        if model := self._model_description:
            self.device_info["model"] = model

        return Data(
            device=device,
            update=update,
            ai_fw_version=ai_fw_version,
            hh_fw_version=hh_fw_version,
            notifications=notifications,
        )


_T = typing.TypeVar("_T")


async def _wait_or_none(awaitable: Awaitable[_T], *, msg: str) -> _T | None:
    try:
        return await awaitable
    except Exception:
        _LOGGER.exception(msg)
        return None
