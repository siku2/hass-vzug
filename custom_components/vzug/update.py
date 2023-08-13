from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import Coordinator, api
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: Coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([VZugUpdate(coordinator)])


class VZugUpdate(UpdateEntity, CoordinatorEntity[Coordinator]):
    _attr_translation_key = "update"
    _attr_has_entity_name = True
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_auto_update = False
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    def __init__(self, coordinator: Coordinator) -> None:
        super().__init__(coordinator)

        self._attr_unique_id = f"{coordinator.unique_id_prefix}-update"
        self._attr_device_info = coordinator.device_info
        self._attr_latest_version = None

    def get_update_component(self) -> api.UpdateComponent | None:
        update = self.coordinator.data.update
        if update is None:
            return None
        components = update["components"]
        for component in components:
            if component["available"]:
                return component
        return None

    @property
    def in_progress(self) -> bool | int | None:
        if component := self.get_update_component():
            if component["running"]:
                progress = component["progress"]
                return (
                    progress.get("download", 0) + progress.get("installation", 0)
                ) // 2
        return False

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        component = self.get_update_component()
        if not component:
            return
        name = component.get("name")
        if not name:
            return

        if name == "AI":
            await self.coordinator.api.do_ai_update()
        elif name == "HHG":
            await self.coordinator.api.do_hhg_update()

    @property
    def installed_version(self) -> str | None:
        if data := self.coordinator.data.ai_fw_version:
            return data.get("SW")
        return None

    @property
    def latest_version(self) -> str | None:
        update = self.coordinator.data.update
        if update is None:
            return None

        if update.get("isAIUpdateAvailable") or update.get("isHHGUpdateAvailable"):
            # we don't have a way to get the newer version, but we know there is one
            return "new version"
        return self.installed_version

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if data := self.coordinator.data.ai_fw_version:
            attrs.update({f"ai_{k}": v for k, v in data.items()})
        if data := self.coordinator.data.hh_fw_version:
            attrs.update({f"hh_{k}": v for k, v in data.items()})
        return attrs
