"""Spond Tracker integration for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ACCOUNTS, CONF_MEMBERS, CONF_PASSWORD, CONF_USERNAME, DOMAIN, PLATFORMS
from .coordinator import SpondDataUpdateCoordinator
from .spond_helpers import dedup_members_by_first_token

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry from v1 (flat credentials) to v2 (accounts list)."""
    if entry.version < 2:
        # Deduplicate members by first-name prefix: "mathias" and "mathias_g"
        # both collapse to canonical "mathias" (the v1 code used member-ID
        # dedup so the same child in two groups could produce two entries).
        deduped_members = dedup_members_by_first_token(entry.data.get(CONF_MEMBERS, []))

        new_data = {
            CONF_ACCOUNTS: [
                {
                    CONF_USERNAME: entry.data[CONF_USERNAME],
                    CONF_PASSWORD: entry.data[CONF_PASSWORD],
                }
            ],
            CONF_MEMBERS: deduped_members,
        }
        hass.config_entries.async_update_entry(entry, data=new_data, version=2)
        _LOGGER.info(
            "Migrated Spond Tracker entry to v2 (multi-account); members: %s",
            [m["canonical"] for m in deduped_members],
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Spond Tracker from a config entry."""
    coordinator = SpondDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
