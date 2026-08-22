"""Spond Tracker integration for Home Assistant."""

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DURATION,
    ATTR_RESPONSE,
    ATTR_TASK,
    ATTR_UNTIL,
    CONF_ACCOUNTS,
    CONF_MEMBERS,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_SNOOZE_HOURS,
    DOMAIN,
    PLATFORMS,
    RESPONSE_ACCEPT,
    RESPONSE_DECLINE,
    SERVICE_RESPOND_TO_TASK,
    SERVICE_SNOOZE_TASK,
)
from .coordinator import SpondDataUpdateCoordinator
from .spond_helpers import dedup_members_by_first_token

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry from v1 (flat credentials) to v2 (accounts list)."""
    if entry.version < 2:
        # Deduplicate members by first-name prefix: "bob" and "bob_g"
        # both collapse to canonical "bob" (the v1 code used member-ID
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


RESPOND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_TASK): cv.string,
        vol.Required(ATTR_RESPONSE): vol.In([RESPONSE_ACCEPT, RESPONSE_DECLINE]),
    }
)

SNOOZE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_TASK): cv.string,
        vol.Exclusive(ATTR_UNTIL, "deadline"): cv.datetime,
        vol.Exclusive(ATTR_DURATION, "deadline"): cv.positive_time_period,
    }
)


def _resolve_members(hass: HomeAssistant, entity_ids: list[str]) -> list[tuple]:
    """Map targeted entities to (coordinator, canonical) pairs.

    Any entity of a tracked member identifies that member, so a dashboard can
    target the tasks sensor it is already showing.
    """
    registry = er.async_get(hass)
    resolved: list[tuple] = []
    for entity_id in entity_ids:
        entry = registry.async_get(entity_id)
        if entry is None or entry.domain not in ("sensor", "calendar"):
            raise ServiceValidationError(f"{entity_id} is not a Spond Tracker entity")
        config_entry = hass.config_entries.async_get_entry(entry.config_entry_id or "")
        if config_entry is None or config_entry.domain != DOMAIN:
            raise ServiceValidationError(f"{entity_id} does not belong to Spond Tracker")
        if config_entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(f"Spond Tracker is not loaded for {entity_id}")
        # unique_id is "<entry_id>_<canonical>_<suffix>"
        unique_id = entry.unique_id or ""
        prefix = f"{config_entry.entry_id}_"
        if not unique_id.startswith(prefix) or "_" not in unique_id[len(prefix) :]:
            raise ServiceValidationError(f"Cannot tell which member {entity_id} belongs to")
        canonical = unique_id[len(prefix) : unique_id.rindex("_")]
        resolved.append((config_entry.runtime_data, canonical))
    return resolved


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions.

    Registered here rather than per entry so they exist — and can explain
    themselves — even while no entry is loaded.
    """

    async def _respond(call: ServiceCall) -> None:
        accepted = call.data[ATTR_RESPONSE] == RESPONSE_ACCEPT
        for coordinator, canonical in _resolve_members(hass, call.data[ATTR_ENTITY_ID]):
            await coordinator.async_respond_to_task(canonical, call.data[ATTR_TASK], accepted)

    async def _snooze(call: ServiceCall) -> None:
        if (until := call.data.get(ATTR_UNTIL)) is not None:
            deadline = dt_util.as_utc(until)
        else:
            duration = call.data.get(ATTR_DURATION, timedelta(hours=DEFAULT_SNOOZE_HOURS))
            deadline = dt_util.utcnow() + duration
        for coordinator, canonical in _resolve_members(hass, call.data[ATTR_ENTITY_ID]):
            await coordinator.async_snooze_task(canonical, call.data[ATTR_TASK], deadline)

    hass.services.async_register(DOMAIN, SERVICE_RESPOND_TO_TASK, _respond, RESPOND_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SNOOZE_TASK, _snooze, SNOOZE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Spond Tracker from a config entry."""
    coordinator = SpondDataUpdateCoordinator(hass, entry)
    await coordinator.async_load_snoozes()
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
