"""Sensor platform for Spond Tracker."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_MEMBERS
from .coordinator import SpondDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SpondDataUpdateCoordinator = entry.runtime_data
    members = entry.data.get(CONF_MEMBERS, [])
    entities: list[SensorEntity] = []
    for member in members:
        entities.append(SpondEventsSensor(coordinator, member))
        entities.append(SpondTasksSensor(coordinator, member))
    async_add_entities(entities)


class SpondEventsSensor(CoordinatorEntity[SpondDataUpdateCoordinator], SensorEntity):
    """Sensor: number of Spond events today for one member."""

    _attr_icon = "mdi:calendar-account"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "events"

    def __init__(self, coordinator: SpondDataUpdateCoordinator, member_cfg: dict) -> None:
        super().__init__(coordinator)
        self._member = member_cfg
        self._canonical = member_cfg["canonical"]
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{self._canonical}_events"
        tmpl = coordinator.strings.get("sensors", {}).get("events_friendly", "Spond {name}")
        self._attr_name = tmpl.format(name=member_cfg["display_name"])

    @property
    def native_value(self) -> int:
        if self.coordinator.data is None:
            return 0
        now_local = dt_util.now()
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        count = 0
        for ev in self.coordinator.data.events.get(self._canonical, []):
            if ev.get("status") in ("cancelled", "declined"):
                continue
            try:
                start = dt_util.parse_datetime((ev.get("start") or "").replace("Z", "+00:00"))
                if start is None:
                    continue
                start_local = dt_util.as_local(start)
                if today_start <= start_local < today_end:
                    count += 1
            except (ValueError, TypeError):
                pass
        return count

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        now_local = dt_util.now()
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        evs = self.coordinator.data.events.get(self._canonical, [])
        visible = [e for e in evs if e.get("status") not in ("declined", "cancelled")]
        today_events = []
        for ev in visible:
            try:
                start = dt_util.parse_datetime((ev.get("start") or "").replace("Z", "+00:00"))
                if start and today_start <= dt_util.as_local(start) < today_end:
                    today_events.append(ev)
            except (ValueError, TypeError):
                pass
        return {
            "today_count": len(today_events),
            "today_events": today_events,
            "next_event": visible[0] if visible else None,
            "upcoming_count": len(visible),
            "upcoming_events": visible[:10],
            "last_updated": self.coordinator.data.polled_at.isoformat(),
        }


class SpondTasksSensor(CoordinatorEntity[SpondDataUpdateCoordinator], SensorEntity):
    """Sensor: number of active Spond tasks assigned to one member."""

    _attr_icon = "mdi:clipboard-list-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "tasks"

    def __init__(self, coordinator: SpondDataUpdateCoordinator, member_cfg: dict) -> None:
        super().__init__(coordinator)
        self._member = member_cfg
        self._canonical = member_cfg["canonical"]
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{self._canonical}_tasks"
        tmpl = coordinator.strings.get("sensors", {}).get("tasks_friendly", "Spond tasks {name}")
        self._attr_name = tmpl.format(name=member_cfg["display_name"])

    @property
    def native_value(self) -> int:
        if self.coordinator.data is None:
            return 0
        tasks = self.coordinator.data.tasks.get(self._canonical, [])
        return sum(1 for t in tasks if not t.get("cancelled"))

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        tasks = self.coordinator.data.tasks.get(self._canonical, [])
        active = [
            {
                "task": t["task_name"],
                "event": t["event_title"],
                "start": t["start"],
                "end": t["end"],
                "location": t["location"],
                "co_assignees": t.get("co_assignees", []),
                "required": t.get("required", 0),
                "assigned_count": t.get("assigned_count", 0),
            }
            for t in tasks
            if not t.get("cancelled")
        ]
        return {"tasks": active}
