"""Smoke tests for Spond Tracker sensor entities."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from custom_components.spond_tracker.coordinator import CoordinatorData
from custom_components.spond_tracker.sensor import SpondEventsSensor, SpondTasksSensor

MEMBER = {"canonical": "alice", "display_name": "Alice Smith"}

NOW = datetime.now(UTC)
TODAY_START = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
FUTURE = NOW + timedelta(hours=2)
TOMORROW = NOW + timedelta(days=1)
YESTERDAY = NOW - timedelta(days=1)


def _make_coordinator(events=None, tasks=None):
    """Build a minimal mock coordinator."""
    entry = MagicMock(spec=["entry_id"])
    entry.entry_id = "test_entry"

    data = CoordinatorData(
        events={"alice": events or []},
        tasks={"alice": tasks or []},
    )
    coord = MagicMock()
    coord.data = data
    coord.last_update_success = True
    coord.strings = {}
    coord.entry = entry
    return coord


def _today_event(status="accepted"):
    return {
        "uid": "evt-today",
        "title": "Training",
        "start": FUTURE.isoformat(),
        "end": TOMORROW.isoformat(),
        "status": status,
        "location": "Field",
        "address": None,
        "my_tasks": [],
        "all_tasks": [],
    }


def _yesterday_event():
    return {
        "uid": "evt-yesterday",
        "title": "Old Event",
        "start": YESTERDAY.isoformat(),
        "end": NOW.isoformat(),
        "status": "accepted",
        "location": None,
        "address": None,
        "my_tasks": [],
        "all_tasks": [],
    }


def _active_task():
    return {
        "task_uid_key": "t1",
        "task_name": "Vakt",
        "event_title": "Kamp",
        "start": FUTURE.isoformat(),
        "end": TOMORROW.isoformat(),
        "location": "Hall",
        "address": None,
        "co_assignees": [],
        "required": 2,
        "assigned_count": 1,
        "cancelled": False,
    }


# ── SpondEventsSensor ─────────────────────────────────────────────────────────


def test_events_sensor_has_translation_key():
    coord = _make_coordinator()
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor._attr_translation_key == "events"
    assert sensor._attr_translation_placeholders == {"name": "Alice Smith"}


def test_events_sensor_unique_id():
    coord = _make_coordinator()
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor._attr_unique_id == "test_entry_alice_events"


def test_events_sensor_counts_todays_events():
    coord = _make_coordinator(events=[_today_event()])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 1


def test_events_sensor_excludes_yesterdays_events():
    coord = _make_coordinator(events=[_yesterday_event()])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


def test_events_sensor_excludes_cancelled():
    coord = _make_coordinator(events=[_today_event(status="cancelled")])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


def test_events_sensor_excludes_declined():
    coord = _make_coordinator(events=[_today_event(status="declined")])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


def test_events_sensor_attributes_structure():
    coord = _make_coordinator(events=[_today_event()])
    sensor = SpondEventsSensor(coord, MEMBER)
    attrs = sensor.extra_state_attributes
    assert "today_count" in attrs
    assert "today_events" in attrs
    assert "next_event" in attrs
    assert "upcoming_count" in attrs
    assert "upcoming_events" in attrs
    assert "last_updated" in attrs


def test_events_sensor_returns_zeros_when_no_data():
    coord = _make_coordinator()
    coord.data = None
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0
    assert sensor.extra_state_attributes == {}


# ── SpondTasksSensor ──────────────────────────────────────────────────────────


def test_tasks_sensor_has_translation_key():
    coord = _make_coordinator()
    sensor = SpondTasksSensor(coord, MEMBER)
    assert sensor._attr_translation_key == "tasks"
    assert sensor._attr_translation_placeholders == {"name": "Alice Smith"}


def test_tasks_sensor_unique_id():
    coord = _make_coordinator()
    sensor = SpondTasksSensor(coord, MEMBER)
    assert sensor._attr_unique_id == "test_entry_alice_tasks"


def test_tasks_sensor_counts_active_tasks():
    coord = _make_coordinator(tasks=[_active_task()])
    sensor = SpondTasksSensor(coord, MEMBER)
    assert sensor.native_value == 1


def test_tasks_sensor_excludes_cancelled_tasks():
    task = _active_task()
    task["cancelled"] = True
    coord = _make_coordinator(tasks=[task])
    sensor = SpondTasksSensor(coord, MEMBER)
    assert sensor.native_value == 0


def test_tasks_sensor_attributes_contain_tasks_list():
    coord = _make_coordinator(tasks=[_active_task()])
    sensor = SpondTasksSensor(coord, MEMBER)
    attrs = sensor.extra_state_attributes
    assert "tasks" in attrs
    assert len(attrs["tasks"]) == 1
    assert attrs["tasks"][0]["task"] == "Vakt"


def test_tasks_sensor_returns_zero_when_no_data():
    coord = _make_coordinator()
    coord.data = None
    sensor = SpondTasksSensor(coord, MEMBER)
    assert sensor.native_value == 0
