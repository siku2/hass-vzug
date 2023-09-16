import asyncio
from collections.abc import Awaitable
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .shared import Shared

TO_REDACT: set[str] = set()


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
            data[key] = await pending
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
        # config aggregate
        do_one("aggregate_config", shared.client.aggregate_config()),
    )

    return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    shared: Shared = hass.data[DOMAIN][entry.entry_id]

    api_sample = await gather_full_api_sample(shared)

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "api_sample": api_sample,
    }
