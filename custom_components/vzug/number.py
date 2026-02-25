from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProgramCoordinator, Shared
from .entity import UserConfigEntity

if TYPE_CHECKING:
    from . import VZugConfigEntry

PARALLEL_UPDATES = 1

_ZONE_FEATURE_TIMERS = ("superCool", "superFreeze", "partyCooling")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: VZugConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    shared = config_entry.runtime_data

    entities: list[NumberEntity] = []

    for category in shared.config_coord.data.values():
        for command in category.commands.values():
            if command.get("type") == "range" and command.get("alterable", True):
                entities.append(
                    UserConfig(
                        shared,
                        category_key=category.key,
                        command_key=command.get("command", ""),
                    )
                )

    if shared.program_coord is not None:
        for zone in shared.program_coord.data.zones:
            zone_name = zone.get("zone", "")
            for feature in _ZONE_FEATURE_TIMERS:
                if feature in zone:
                    entities.append(
                        ZoneFeatureTimer(
                            shared,
                            zone_name=zone_name,
                            feature=feature,
                            limits=zone[feature],
                        )
                    )

    async_add_entities(entities)


class UserConfig(NumberEntity, UserConfigEntity):
    _attr_mode = NumberMode.SLIDER

    @property
    def native_min_value(self) -> float:
        try:
            return float(self.vzug_command["minMax"][0])
        except (ValueError, LookupError, TypeError):
            return 0.0

    @property
    def native_max_value(self) -> float:
        try:
            return float(self.vzug_command["minMax"][1])
        except (ValueError, LookupError, TypeError):
            return 0.0

    @property
    def native_step(self) -> float | None:
        return 1.0

    @property
    def native_value(self) -> float | None:
        value = self.vzug_command.get("value")
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.shared.client.set_command(self.vzug_command_key, str(int(value)))
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_command_failed",
                translation_placeholders={
                    "command_key": self.vzug_command_key,
                    "error": str(err),
                },
            ) from err
        await self.coordinator.async_request_refresh()


class ZoneFeatureTimer(NumberEntity, CoordinatorEntity[ProgramCoordinator]):
    _attr_has_entity_name = True
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = "s"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        shared: Shared,
        *,
        zone_name: str,
        feature: str,
        limits: dict[str, int],
    ) -> None:
        assert shared.program_coord is not None
        super().__init__(shared.program_coord)
        self.shared = shared
        self.vzug_zone_name = zone_name
        self.vzug_feature = feature

        self._attr_translation_key = f"{feature.lower()}_{zone_name}"
        self._attr_unique_id = (
            f"{shared.unique_id_prefix}-number-{self.translation_key}"
        )
        self._attr_device_info = shared.device_info
        self._attr_native_min_value = float(limits.get("min", 0))
        self._attr_native_max_value = float(limits.get("max", 0))

    @property
    def native_value(self) -> float | None:
        for zone in self.coordinator.data.zones:
            if zone.get("zone") == self.vzug_zone_name:
                feature_data = zone.get(self.vzug_feature)
                if feature_data is None:
                    return None
                # Current value might be in 'set' or 'act' key, or just min/max
                if "set" in feature_data:
                    return float(feature_data["set"])
                if "act" in feature_data:
                    return float(feature_data["act"])
                return None
        return None

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.shared.client.set_program(
                0, {self.vzug_feature: int(value), "zone": self.vzug_zone_name}
            )
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="set_command_failed",
                translation_placeholders={
                    "command_key": self.vzug_feature,
                    "error": str(err),
                },
            ) from err
        await self.coordinator.async_request_refresh()
