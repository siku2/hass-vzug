import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from yarl import URL

from . import api
from .const import CONF_BASE_URL, DOMAIN
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
    base_url = URL(entry.data[CONF_BASE_URL])
    try:
        credentials = api.Credentials(
            username=entry.data[CONF_USERNAME], password=entry.data[CONF_PASSWORD]
        )
    except KeyError:
        credentials = None
    shared = Shared(hass, base_url, credentials)
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


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    version_tuple = (entry.version, entry.minor_version)
    _LOGGER.debug("migrating from version %s.%s", entry.version, entry.minor_version)

    if version_tuple > (2, 2):
        # downgrade is not supported
        return False

    new_data = entry.data.copy()

    if version_tuple < (2, 0):
        # version 2 switched from using 'host' to 'base_url' in the config to allow for http / https differentiation
        base_url = URL(new_data.pop("host"))
        if not base_url.is_absolute():
            base_url = URL(f"http://{base_url}")
        new_data[CONF_BASE_URL] = str(base_url)

    if version_tuple < (2, 2):
        # version 2.2 switches from using 'device_uuid' or 'device_serial' to 'mac_addr' in the unique_id
        entity_reg = er.async_get(hass)
        entities = er.async_entries_for_config_entry(entity_reg, entry.entry_id)

        # setup coordinator to get required data for unique_id
        try:
            credentials = api.Credentials(
                username=new_data[CONF_USERNAME],
                password=new_data[CONF_PASSWORD],
            )
        except KeyError:
            credentials = None
        base_url = URL(new_data[CONF_BASE_URL])
        shared = Shared(hass, base_url, credentials)
        await shared.async_config_entry_first_refresh()

        old_prefix = shared.state_coord.data.device.get(
            "deviceUuid", ""
        ) or shared.state_coord.data.device.get("Serial", "")
        mac_addr = dr.format_mac(shared.meta.mac_address)

        for entity in entities:
            # migrate unique_id_prefix from 'device_uuid' or 'device_serial' to 'mac_addr'
            if old_prefix not in entity.unique_id:
                continue

            new_uid = entity.unique_id.replace(old_prefix, mac_addr)
            _LOGGER.debug("migrate unique id '%s' to '%s'", entity.unique_id, new_uid)
            entity_reg.async_update_entity(entity.entity_id, new_unique_id=new_uid)

    hass.config_entries.async_update_entry(
        entry,
        data=new_data,
        version=2,
        minor_version=2,
    )

    _LOGGER.debug(
        "migration to version %s.%s successful",
        entry.version,
        entry.minor_version,
    )

    return True
