"""Calendar platform for Spond Tracker."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MEMBERS
from .coordinator import SpondDataUpdateCoordinator
from .spond_helpers import stable_uid_for
from .spond_i18n import STATUS_EMOJI, TASK_MARKER

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SpondDataUpdateCoordinator = entry.runtime_data
    members = entry.data.get(CONF_MEMBERS, [])
    async_add_entities(SpondCalendarEntity(coordinator, member) for member in members)


class SpondCalendarEntity(CoordinatorEntity[SpondDataUpdateCoordinator], CalendarEntity):
    """A calendar entity for one tracked Spond member."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SpondDataUpdateCoordinator, member_cfg: dict) -> None:
        super().__init__(coordinator)
        self._member = member_cfg
        self._canonical = member_cfg["canonical"]
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{self._canonical}_calendar"
        self._attr_name = member_cfg["display_name"]

    def _t(self, key: str, **fmt: object) -> str:
        cur: object = self.coordinator.strings
        for part in key.split("."):
            if not isinstance(cur, dict):
                return key
            cur = cur.get(part)
            if cur is None:
                return key
        if not isinstance(cur, str):
            return key
        return cur.format(**fmt) if fmt else cur

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming visible event."""
        if self.coordinator.data is None:
            return None
        now = datetime.now(UTC)
        events = self.coordinator.data.events.get(self._canonical, [])
        # Prefer an event currently in progress over a future one
        for ev in events:
            if ev.get("status") in ("declined",):
                continue
            start_dt, end_dt = _parse_event_times(ev)
            if start_dt is None or end_dt is None:
                continue
            if start_dt <= now < end_dt:
                return self._to_calendar_event(ev)
        for ev in events:
            if ev.get("status") in ("declined",):
                continue
            start_dt, end_dt = _parse_event_times(ev)
            if start_dt is None or end_dt is None:
                continue
            if start_dt > now:
                return self._to_calendar_event(ev)
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return all events (and tasks) in the requested date range."""
        if self.coordinator.data is None:
            return []

        result: list[CalendarEvent] = []

        for ev in self.coordinator.data.events.get(self._canonical, []):
            if ev.get("status") == "declined":
                continue
            start_dt, end_dt = _parse_event_times(ev)
            if start_dt is None or end_dt is None:
                continue
            if end_dt <= start_date or start_dt >= end_date:
                continue
            result.append(self._to_calendar_event(ev))

        for task in self.coordinator.data.tasks.get(self._canonical, []):
            if task.get("cancelled"):
                continue
            start_dt, end_dt = _parse_task_times(task)
            if start_dt is None or end_dt is None:
                continue
            if end_dt <= start_date or start_dt >= end_date:
                continue
            result.append(self._to_task_calendar_event(task))

        return sorted(result, key=lambda e: e.start)

    def _to_calendar_event(self, ev: dict) -> CalendarEvent:
        start_dt, end_dt = _parse_event_times(ev)
        status = ev.get("status", "unknown")
        emoji = STATUS_EMOJI.get(status, "")

        if status == "cancelled":
            summary = f"{emoji} {self._t('calendar.cancelled_prefix')}{ev['title']}".strip()
        else:
            summary = f"{emoji} {ev['title']}".strip()

        desc_parts = [f"{self._t('calendar.status_label')}: {self._t(f'calendar.status_{status}')}"]
        if ev.get("location"):
            desc_parts.append(f"{self._t('calendar.location_label')}: {ev['location']}")
        if ev.get("address"):
            desc_parts.append(f"{self._t('calendar.address_label')}: {ev['address']}")

        if ev.get("my_tasks"):
            lines = [self._t("calendar.my_tasks_header")]
            for t in ev["my_tasks"]:
                suffix = ""
                if t.get("required"):
                    suffix = (
                        f" ({t['assigned_count']}/{t['required']} "
                        f"{self._t('calendar.signed_up_suffix')})"
                    )
                co = t.get("co_assignees") or []
                co_str = (
                    f" — {self._t('calendar.co_assignees_with')}: {', '.join(co)}" if co else ""
                )
                lines.append(f"  • {t['name']}{suffix}{co_str}")
            desc_parts.append("\n".join(lines))

        if ev.get("all_tasks"):
            lines = [self._t("calendar.all_tasks_header")]
            for t in ev["all_tasks"]:
                assigned = t.get("assigned") or []
                if t.get("required"):
                    status_str = f"{len(assigned)}/{t['required']}" + (
                        f" — {self._t('calendar.open_slot')}" if t["is_open"] else ""
                    )
                else:
                    status_str = f"{len(assigned)} {self._t('calendar.signed_up_suffix')}"
                names = f": {', '.join(assigned)}" if assigned else ""
                adults = f" ({self._t('calendar.adults_only')})" if t.get("adults_only") else ""
                lines.append(f"  • {t['name']} [{status_str}]{adults}{names}")
            desc_parts.append("\n".join(lines))

        return CalendarEvent(
            start=start_dt,
            end=end_dt,
            summary=summary,
            description="\n".join(desc_parts) or None,
            location=ev.get("location") or None,
            uid=stable_uid_for(ev["uid"], self._canonical),
        )

    def _to_task_calendar_event(self, task: dict) -> CalendarEvent:
        start_dt, end_dt = _parse_task_times(task)
        summary = f"{TASK_MARKER} {task['task_name']} — {task['event_title']}"

        desc_parts = [
            f"{self._t('calendar.task_for')} {self._member.get('display_name', self._canonical.title())}",
            f"{self._t('calendar.on_event')}: {task['event_title']}",
        ]
        if task.get("required"):
            desc_parts.append(
                f"{self._t('calendar.task_signed_up')}: {task['assigned_count']}/{task['required']}"
            )
        if task.get("co_assignees"):
            desc_parts.append(f"{self._t('calendar.task_with')}: {', '.join(task['co_assignees'])}")
        if task.get("location"):
            desc_parts.append(f"{self._t('calendar.location_label')}: {task['location']}")
        if task.get("address"):
            desc_parts.append(f"{self._t('calendar.address_label')}: {task['address']}")
        if task.get("cancelled"):
            desc_parts.append(self._t("calendar.main_event_cancelled"))

        return CalendarEvent(
            start=start_dt,
            end=end_dt,
            summary=summary,
            description="\n".join(desc_parts) or None,
            location=task.get("location") or None,
            uid=stable_uid_for(f"task::{task['task_uid_key']}", self._canonical),
        )


def _parse_event_times(ev: dict) -> tuple[datetime | None, datetime | None]:
    try:
        start = datetime.fromisoformat((ev.get("start") or "").replace("Z", "+00:00"))
        end = datetime.fromisoformat((ev.get("end") or "").replace("Z", "+00:00"))
        return start, end
    except (ValueError, TypeError):
        return None, None


def _parse_task_times(task: dict) -> tuple[datetime | None, datetime | None]:
    try:
        start = datetime.fromisoformat((task.get("start") or "").replace("Z", "+00:00"))
        end = datetime.fromisoformat((task.get("end") or "").replace("Z", "+00:00"))
        return start, end
    except (ValueError, TypeError):
        return None, None
