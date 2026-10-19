from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import api
from .const import DOMAIN
from .shared import Shared, UpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared: Shared = hass.data[DOMAIN][config_entry.entry_id]

    if shared.meta.supports_update_status():
        async_add_entities([VZugUpdate(shared)])


class VZugUpdate(UpdateEntity, CoordinatorEntity[UpdateCoordinator]):
    _attr_translation_key = "update"
    _attr_has_entity_name = True
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_auto_update = False
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    )

    shared: Shared

    def __init__(self, shared: Shared) -> None:
        super().__init__(shared.update_coord)
        self.shared = shared

        self._attr_unique_id = f"{shared.unique_id_prefix}-update"
        self._attr_device_info = shared.device_info
        self._last_installed: str | None = None
        self._last_latest: str | None = None
        self._attr_latest_version = self._latest_version()

    def get_update_component(self) -> api.UpdateComponent:
        try:
            components = self.coordinator.data.update["components"]
        except LookupError:
            components = []

        for component in components:
            if component.get("available", False):
                return component
        return api.UpdateComponent()

    @property
    def in_progress(self) -> bool | int | None:
        component = self.get_update_component()
        if not component.get("running", False):
            return False

        try:
            progress = component["progress"]
        except LookupError:
            progress = api.UpdateProgress()

        return (progress.get("download", 0) + progress.get("installation", 0)) // 2

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        component = self.get_update_component()
        name = component.get("name")
        if not name:
            return

        if name == "AI":
            await self.shared.client.do_ai_update()
        elif name == "HHG":
            await self.shared.client.do_hhg_update()
        else:
            raise ValueError("unknown update component", name)
        # the status may still read 'idle' right after the request, which would
        # put the coordinator back on its idle interval before the run even starts
        self.shared.note_update_activity()
        await self.coordinator.async_request_refresh()

    @property
    def installed_version(self) -> str | None:
        return self.coordinator.data.ai_fw_version.get("SW")

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_latest_version = self._latest_version()
        super()._handle_coordinator_update()

    def _latest_version(self) -> str | None:
        data = self.coordinator.data
        installed = self.installed_version
        if not installed:
            return None

        if not data.update or (
            data.update.get("isHHGUpdateAvailable") and not data.hh_fw_version
        ):
            # a request failed ('default_on_error' turns it into an empty response).
            # Answering from what's left would differ from a skipped placeholder and
            # release the skip, so stick to the last full answer while it still
            # describes the installed firmware.
            if installed == self._last_installed:
                return self._last_latest
            return None

        # we don't have a way to get the newer version, only that there is one. HA
        # stores whatever this returns when the user presses 'Skip' and releases the
        # skip once it changes, so the placeholder names what is installed for each
        # pending component: a new firmware or another pending component ends it.
        pending: list[str] = []
        if data.update.get("isAIUpdateAvailable"):
            pending.append(installed)
        if data.update.get("isHHGUpdateAvailable"):
            pending.append(data.hh_fw_version.get("v") or "HHG")
        latest = "newer than " + ", ".join(pending) if pending else installed

        self._last_installed, self._last_latest = installed, latest
        return latest

    def version_is_newer(self, latest_version: str, installed_version: str) -> bool:
        # 'latest_version' only differs from the installed one when the appliance
        # reports an update. Don't rely on AwesomeVersion failing to parse the
        # placeholder to get there.
        return latest_version != installed_version

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        attrs.update(
            {f"ai_{k}": v for k, v in self.coordinator.data.ai_fw_version.items()}
        )
        attrs.update(
            {f"hh_{k}": v for k, v in self.coordinator.data.hh_fw_version.items()}
        )
        return attrs
