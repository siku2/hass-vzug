"""Diagnostics of an appliance, with a sample of everything its API answers."""

import asyncio
import dataclasses
from collections.abc import Awaitable
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_BASE_URL
from .coordinator import Shared, VZugConfigEntry

TO_REDACT: set[str] = {
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_BASE_URL,
    "unique_id",
    "title",
    "discovery_keys",
    "mac_address",
    "deviceUuid",
    "Serial",
    "serialNumber",
    "serial_number",
    "articleNumber",
    "DeviceName",
    "device_name",
    "fn",
    "an",
}


def _serialize_exception(exc: Exception) -> dict[str, Any]:
    return {
        "type": type(exc).__qualname__,
        "message": str(exc),
        "args": exc.args,
    }


async def gather_full_api_sample(shared: Shared) -> dict[str, Any]:
    data: dict[str, Any] = {}

    async def do_one(key: str, pending: Awaitable[Any]) -> None:
        try:
            data[key] = _jsonable(await pending)
        except Exception as exc:
            data[key] = _serialize_exception(exc)

    await asyncio.gather(
        do_one("mac_address", shared.client.get_mac_address()),
        do_one("model_description", shared.client.get_model_description()),
        do_one("device_status", shared.client.get_device_status()),
        do_one("update_status", shared.client.get_update_status()),
        do_one("check_for_updates", shared.client.check_for_updates()),
        do_one("last_push_notifications", shared.client.get_last_push_notifications()),
        do_one("list_categories", shared.client.list_categories()),
        do_one("hh_fw_version", shared.client.get_hh_fw_version()),
        do_one("ai_fw_version", shared.client.get_ai_fw_version()),
        do_one("zh_mode", shared.client.get_zh_mode()),
        do_one("eco_info", shared.client.get_eco_info()),
        do_one("device_info", shared.client.get_device_info()),
        do_one("program", shared.client.get_program()),
        do_one("all_program_ids", shared.client.get_all_program_ids()),
        do_one("api_version_ai", shared.client.get_api_version("ai")),
        do_one("api_version_hh", shared.client.get_api_version("hh")),
        do_one("errors", shared.client.get_errors()),
        do_one("installed_features", shared.client.get_installed_features()),
        do_one("aggregate_config", shared.client.aggregate_config()),
    )

    return data


def _jsonable(value: Any) -> Any:
    """Dataclasses (the aggregated config tree) as plain data."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _coordinators(shared: Shared) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for coordinator in (
        shared.state_coord,
        shared.update_coord,
        shared.config_coord,
        shared.zone_coord,
        shared.program_coord,
    ):
        if coordinator is None:
            continue
        interval = coordinator.update_interval
        result[coordinator.name] = {
            "last_update_success": coordinator.last_update_success,
            "update_interval": interval.total_seconds() if interval else None,
            "last_exception": repr(coordinator.last_exception)
            if coordinator.last_exception
            else None,
        }
    return result


def _scrub(data: Any, secrets: list[str]) -> Any:
    """Replace the appliance's address (in error messages, URLs) everywhere."""
    if isinstance(data, str):
        for secret in secrets:
            data = data.replace(secret, "**REDACTED**")
        return data
    if isinstance(data, dict):
        return {key: _scrub(value, secrets) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [_scrub(value, secrets) for value in data]
    return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VZugConfigEntry
) -> dict[str, Any]:
    shared = entry.runtime_data

    api_sample = await gather_full_api_sample(shared)

    data = {
        "entry": entry.as_dict(),
        "meta": dataclasses.asdict(shared.meta),
        "coordinators": _coordinators(shared),
        "api_sample": api_sample,
    }
    secrets = [
        str(secret)
        for secret in (
            shared.client.base_url.host,
            shared.meta.mac_address,
            shared.meta.serial_number,
        )
        if secret
    ]
    return async_redact_data(_scrub(data, secrets), TO_REDACT)
