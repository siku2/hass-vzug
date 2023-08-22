import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from yarl import URL

from .const import DOMAIN
from .shared import Shared

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up V-ZUG from a config entry."""
    base_url = URL(entry.data["base_url"])
    shared = Shared(hass, base_url)
    await shared.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = shared

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        shared: Shared
        if shared := hass.data[DOMAIN].pop(entry.entry_id):
            await shared.async_shutdown()

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    _LOGGER.debug("migrating from version %s", config_entry.version)

    if config_entry.version == 1:
        base_url = URL(config_entry.data["host"])
        if not base_url.is_absolute():
            base_url = URL(f"http://{base_url}")

        config_entry.version = 2
        hass.config_entries.async_update_entry(
            config_entry, data={"base_url": str(base_url)}
        )

    _LOGGER.info("migration to version %s successful", config_entry.version)

    return True
