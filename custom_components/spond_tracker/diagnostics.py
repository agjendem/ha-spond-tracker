"""Diagnostics support for Spond Tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCOUNTS,
    CONF_MEMBERS,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
)
from .coordinator import SpondDataUpdateCoordinator

_TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: SpondDataUpdateCoordinator = entry.runtime_data
    data = coordinator.data

    accounts = [async_redact_data(acc, _TO_REDACT) for acc in entry.data.get(CONF_ACCOUNTS, [])]
    members = entry.data.get(CONF_MEMBERS, [])

    return {
        "account_count": len(accounts),
        "accounts": accounts,
        "member_count": len(members),
        "members": [m["canonical"] for m in members],
        "poll_interval_minutes": entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        "language": coordinator.language,
        "last_polled": data.polled_at.isoformat() if data else None,
        "events_per_member": {c: len(evs) for c, evs in data.events.items()} if data else {},
        "tasks_per_member": {c: len(tks) for c, tks in data.tasks.items()} if data else {},
    }
