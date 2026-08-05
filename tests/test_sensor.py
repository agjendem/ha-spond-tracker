"""Smoke tests for Spond Tracker sensor entities."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.spond_tracker.coordinator import CoordinatorData
from custom_components.spond_tracker.sensor import SpondEventsSensor, SpondTasksSensor

MEMBER = {"canonical": "alice", "display_name": "Alice Smith"}

# Fixed reference point at noon UTC — avoids midnight boundary flakiness in CI.
NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
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
    """An event that both started and finished yesterday."""
    return {
        "uid": "evt-yesterday",
        "title": "Old Event",
        "start": YESTERDAY.isoformat(),
        "end": (YESTERDAY + timedelta(hours=2)).isoformat(),
        "status": "accepted",
        "location": None,
        "address": None,
        "my_tasks": [],
        "all_tasks": [],
    }


def _multiday_event(start, end, status="accepted"):
    """An event spanning a range, e.g. a camp running over several days."""
    return {
        "uid": "evt-multiday",
        "title": "Camp",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "status": status,
        "location": "Ishall",
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


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_counts_todays_events():
    coord = _make_coordinator(events=[_today_event()])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 1


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_excludes_yesterdays_events():
    coord = _make_coordinator(events=[_yesterday_event()])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


# ── Multi-day events ──────────────────────────────────────────────────────────
#
# An event is "today" when it *overlaps* today, not when it *starts* today.
# A camp running Tue-Thu is happening on Wednesday too. Counting by start time
# made every such event invisible on every day except the one it began.


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_counts_ongoing_multiday_event():
    """An event that began before today and ends after today still counts."""
    coord = _make_coordinator(events=[_multiday_event(YESTERDAY, TOMORROW)])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 1


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_counts_multiday_event_on_its_final_day():
    """The closing day of a multi-day event counts, even though it started earlier."""
    coord = _make_coordinator(events=[_multiday_event(YESTERDAY, NOW + timedelta(hours=3))])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 1


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_counts_multiday_event_on_its_first_day():
    """Starting today and running on for days still counts today."""
    coord = _make_coordinator(events=[_multiday_event(FUTURE, TOMORROW + timedelta(days=2))])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 1


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_excludes_multiday_event_that_ended_before_today():
    coord = _make_coordinator(
        events=[_multiday_event(YESTERDAY - timedelta(days=3), YESTERDAY - timedelta(hours=1))]
    )
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_excludes_multiday_event_starting_after_today():
    coord = _make_coordinator(
        events=[_multiday_event(TOMORROW + timedelta(hours=1), TOMORROW + timedelta(days=3))]
    )
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_still_excludes_declined_multiday_event():
    """Overlap must not resurrect events the member declined."""
    coord = _make_coordinator(events=[_multiday_event(YESTERDAY, TOMORROW, status="declined")])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_ongoing_multiday_event_appears_in_today_events_attribute():
    """The attribute the dashboards read must agree with the sensor state."""
    coord = _make_coordinator(events=[_multiday_event(YESTERDAY, TOMORROW)])
    sensor = SpondEventsSensor(coord, MEMBER)
    attrs = sensor.extra_state_attributes
    assert attrs["today_count"] == 1
    assert [e["uid"] for e in attrs["today_events"]] == ["evt-multiday"]
    assert attrs["today_count"] == sensor.native_value


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_camp_spanning_yesterday_to_tomorrow_is_visible_today():
    """Regression: the reported case.

    A camp from 09:00 the day before yesterday until 15:00 tomorrow was
    reported as 0 events today, while the calendar entity correctly showed it
    as in progress.
    """
    start = datetime(2026, 6, 13, 9, 0, tzinfo=UTC)
    end = datetime(2026, 6, 16, 15, 0, tzinfo=UTC)
    coord = _make_coordinator(events=[_multiday_event(start, end)])
    sensor = SpondEventsSensor(coord, MEMBER)

    assert sensor.native_value == 1
    assert sensor.extra_state_attributes["today_count"] == 1


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_counts_event_without_end_on_its_start_day():
    """An event with no usable end is treated as happening at a single instant."""
    ev = _multiday_event(FUTURE, TOMORROW)
    ev["end"] = None
    coord = _make_coordinator(events=[ev])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 1

    ev_yesterday = _multiday_event(YESTERDAY, TOMORROW)
    ev_yesterday["end"] = None
    coord = _make_coordinator(events=[ev_yesterday])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_ignores_unparseable_timestamps():
    ev = _multiday_event(YESTERDAY, TOMORROW)
    ev["start"] = "not a timestamp"
    coord = _make_coordinator(events=[ev])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_excludes_cancelled():
    coord = _make_coordinator(events=[_today_event(status="cancelled")])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


@pytest.mark.freeze_time("2026-06-15 12:00:00")
def test_events_sensor_excludes_declined():
    coord = _make_coordinator(events=[_today_event(status="declined")])
    sensor = SpondEventsSensor(coord, MEMBER)
    assert sensor.native_value == 0


@pytest.mark.freeze_time("2026-06-15 12:00:00")
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
