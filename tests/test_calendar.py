"""Smoke tests for Spond Tracker calendar entity."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from custom_components.spond_tracker.calendar import SpondCalendarEntity
from custom_components.spond_tracker.coordinator import CoordinatorData

MEMBER = {"canonical": "alice", "display_name": "Alice Smith"}

NOW = datetime.now(UTC)
PAST = NOW - timedelta(hours=3)
FUTURE = NOW + timedelta(hours=2)
LATER = NOW + timedelta(hours=4)
NEXT_WEEK = NOW + timedelta(days=7)
NEXT_WEEK_END = NOW + timedelta(days=7, hours=2)

EN_STRINGS = {
    "calendar": {
        "cancelled_prefix": "CANCELLED: ",
        "status_label": "Status",
        "location_label": "Location",
        "address_label": "Address",
        "my_tasks_header": "My tasks:",
        "all_tasks_header": "All tasks:",
        "signed_up_suffix": "signed up",
        "open_slot": "OPEN",
        "adults_only": "adults only",
        "co_assignees_with": "with",
        "task_for": "Task for",
        "on_event": "On event",
        "task_signed_up": "Signed up",
        "task_with": "With",
        "main_event_cancelled": "⚠️ Main event is CANCELLED",
        "status_accepted": "Accepted",
        "status_declined": "Declined",
        "status_cancelled": "Cancelled",
        "status_waitinglist": "Waitinglist",
        "status_unanswered": "Unanswered",
        "status_unknown": "Unknown",
    }
}


def _make_coordinator(events=None, tasks=None):
    entry = MagicMock(spec=["entry_id"])
    entry.entry_id = "test_entry"
    data = CoordinatorData(
        events={"alice": events or []},
        tasks={"alice": tasks or []},
    )
    coord = MagicMock()
    coord.data = data
    coord.last_update_success = True
    coord.strings = EN_STRINGS
    coord.entry = entry
    return coord


def _event(uid, title, start, end, status="accepted", location=None, address=None):
    return {
        "uid": uid,
        "title": title,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "status": status,
        "location": location,
        "address": address,
        "my_tasks": [],
        "all_tasks": [],
    }


def _task(uid_key, task_name, event_title, start, end):
    return {
        "task_uid_key": uid_key,
        "task_name": task_name,
        "event_title": event_title,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "location": None,
        "address": None,
        "co_assignees": [],
        "required": 0,
        "assigned_count": 0,
        "cancelled": False,
    }


# ── event property ────────────────────────────────────────────────────────────


def test_event_returns_none_when_no_data():
    coord = _make_coordinator()
    coord.data = None
    cal = SpondCalendarEntity(coord, MEMBER)
    assert cal.event is None


def test_event_returns_none_when_no_events():
    cal = SpondCalendarEntity(_make_coordinator(), MEMBER)
    assert cal.event is None


def test_event_returns_in_progress_event():
    ev = _event("e1", "Training", PAST, LATER)
    cal = SpondCalendarEntity(_make_coordinator(events=[ev]), MEMBER)
    ce = cal.event
    assert ce is not None
    assert "Training" in ce.summary


def test_event_returns_next_upcoming_when_none_in_progress():
    ev = _event("e1", "Match", FUTURE, LATER)
    cal = SpondCalendarEntity(_make_coordinator(events=[ev]), MEMBER)
    ce = cal.event
    assert ce is not None
    assert "Match" in ce.summary


def test_event_skips_declined():
    declined = _event("e1", "Old", FUTURE, LATER, status="declined")
    upcoming = _event("e2", "Training", NEXT_WEEK, NEXT_WEEK_END)
    cal = SpondCalendarEntity(_make_coordinator(events=[declined, upcoming]), MEMBER)
    ce = cal.event
    assert ce is not None
    assert "Training" in ce.summary


# ── async_get_events ──────────────────────────────────────────────────────────


async def test_async_get_events_returns_events_in_range():
    ev_in = _event("e1", "Training", FUTURE, LATER)
    ev_out = _event("e2", "Old", NOW - timedelta(days=10), NOW - timedelta(days=9))
    cal = SpondCalendarEntity(_make_coordinator(events=[ev_in, ev_out]), MEMBER)
    results = await cal.async_get_events(None, NOW, NEXT_WEEK)
    assert len(results) == 1
    assert "Training" in results[0].summary


async def test_async_get_events_excludes_declined():
    ev = _event("e1", "Declined", FUTURE, LATER, status="declined")
    cal = SpondCalendarEntity(_make_coordinator(events=[ev]), MEMBER)
    results = await cal.async_get_events(None, NOW, NEXT_WEEK)
    assert len(results) == 0


async def test_async_get_events_includes_tasks():
    task = _task("t1", "Vakt", "Kamp", FUTURE, LATER)
    cal = SpondCalendarEntity(_make_coordinator(tasks=[task]), MEMBER)
    results = await cal.async_get_events(None, NOW, NEXT_WEEK)
    assert len(results) == 1
    assert "Vakt" in results[0].summary


async def test_async_get_events_returns_empty_when_no_data():
    coord = _make_coordinator()
    coord.data = None
    cal = SpondCalendarEntity(coord, MEMBER)
    results = await cal.async_get_events(None, NOW, NEXT_WEEK)
    assert results == []


# ── event description formatting ─────────────────────────────────────────────


def test_cancelled_event_has_prefix_in_summary():
    ev = _event("e1", "Training", FUTURE, LATER, status="cancelled")
    cal = SpondCalendarEntity(_make_coordinator(events=[ev]), MEMBER)
    ce = cal._to_calendar_event(ev)
    assert "CANCELLED" in ce.summary


def test_accepted_event_has_no_cancel_prefix():
    ev = _event("e1", "Training", FUTURE, LATER)
    cal = SpondCalendarEntity(_make_coordinator(events=[ev]), MEMBER)
    ce = cal._to_calendar_event(ev)
    assert "CANCELLED" not in ce.summary


def test_event_description_includes_status():
    ev = _event("e1", "Training", FUTURE, LATER)
    cal = SpondCalendarEntity(_make_coordinator(events=[ev]), MEMBER)
    ce = cal._to_calendar_event(ev)
    assert "Status" in ce.description
    assert "Accepted" in ce.description


def test_event_description_includes_location():
    ev = _event("e1", "Training", FUTURE, LATER, location="Stadion")
    cal = SpondCalendarEntity(_make_coordinator(events=[ev]), MEMBER)
    ce = cal._to_calendar_event(ev)
    assert "Stadion" in ce.description


def test_event_uid_is_stable():
    ev = _event("e1", "Training", FUTURE, LATER)
    cal = SpondCalendarEntity(_make_coordinator(events=[ev]), MEMBER)
    ce1 = cal._to_calendar_event(ev)
    ce2 = cal._to_calendar_event(ev)
    assert ce1.uid == ce2.uid
