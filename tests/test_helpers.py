"""Tests for spond_helpers."""

from datetime import UTC, datetime

import pytest
from spond_helpers import (
    event_fingerprint,
    fmt_dt,
    ics_escape,
    read_past_event_blocks,
    stable_uid_for,
)


class TestFmtDt:
    def test_z_suffix(self) -> None:
        assert fmt_dt("2026-05-30T12:34:56Z") == "20260530T123456Z"

    def test_offset_normalized_to_utc(self) -> None:
        # 12:34 +02:00 -> 10:34 UTC
        assert fmt_dt("2026-05-30T12:34:56+02:00") == "20260530T103456Z"

    def test_offset_negative(self) -> None:
        # 12:34 -05:00 -> 17:34 UTC
        assert fmt_dt("2026-05-30T12:34:56-05:00") == "20260530T173456Z"

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            fmt_dt("not-a-date")


class TestStableUidFor:
    def test_deterministic(self) -> None:
        a = stable_uid_for("evt-123", "alice")
        b = stable_uid_for("evt-123", "alice")
        assert a == b

    def test_different_canonical_different_uid(self) -> None:
        a = stable_uid_for("evt-123", "alice")
        b = stable_uid_for("evt-123", "bob")
        assert a != b

    def test_different_event_different_uid(self) -> None:
        a = stable_uid_for("evt-123", "alice")
        b = stable_uid_for("evt-456", "alice")
        assert a != b

    def test_format(self) -> None:
        uid = stable_uid_for("evt-x", "alice")
        # 32-char md5 hex + "@spond-sync.local"
        assert uid.endswith("@spond-sync.local")
        local_part = uid.split("@", 1)[0]
        assert len(local_part) == 32
        assert all(c in "0123456789abcdef" for c in local_part)


class TestIcsEscape:
    def test_none_returns_empty(self) -> None:
        assert ics_escape(None) == ""

    def test_empty_string_unchanged(self) -> None:
        assert ics_escape("") == ""

    def test_no_special_chars_unchanged(self) -> None:
        assert ics_escape("Plain text") == "Plain text"

    def test_comma_escaped(self) -> None:
        assert ics_escape("a, b, c") == "a\\, b\\, c"

    def test_semicolon_escaped(self) -> None:
        assert ics_escape("a; b") == "a\\; b"

    def test_newline_escaped(self) -> None:
        assert ics_escape("line1\nline2") == "line1\\nline2"

    def test_backslash_escaped_first(self) -> None:
        # Backslash must be escaped before the others to avoid double-escaping.
        assert ics_escape("a\\b") == "a\\\\b"

    def test_combination(self) -> None:
        assert ics_escape("Hi, world;\nbye") == "Hi\\, world\\;\\nbye"


class TestEventFingerprint:
    def _base_event(self) -> dict:
        return {
            "title": "Practice",
            "start": "2026-05-30T18:00:00Z",
            "end": "2026-05-30T19:30:00Z",
            "location": "Hall A",
            "status": "accepted",
            "my_tasks": [],
            "all_tasks": [],
            "open_tasks_count": 0,
        }

    def test_minimal_event(self) -> None:
        fp = event_fingerprint(self._base_event())
        assert fp["title"] == "Practice"
        assert fp["my_tasks"] == ()
        assert fp["all_tasks"] == ()

    def test_my_tasks_sorted_tuple(self) -> None:
        e = self._base_event()
        e["my_tasks"] = [{"name": "Banana"}, {"name": "Apple"}]
        fp = event_fingerprint(e)
        # Sorted alphabetically, frozen as tuple for hashability
        assert fp["my_tasks"] == ("Apple", "Banana")

    def test_all_tasks_includes_assignment_state(self) -> None:
        e = self._base_event()
        e["all_tasks"] = [
            {"name": "Bake", "assigned": ["Alice", "Bob"], "required": 2},
            {"name": "Drive", "assigned": ["Carol"], "required": 1},
        ]
        fp = event_fingerprint(e)
        # Each task: "name:assigned_count/required"
        assert fp["all_tasks"] == ("Bake:2/2", "Drive:1/1")

    def test_difference_detected_on_title(self) -> None:
        a = event_fingerprint(self._base_event())
        e2 = self._base_event()
        e2["title"] = "Game"
        b = event_fingerprint(e2)
        assert a != b

    def test_difference_detected_on_task_assignment(self) -> None:
        e1 = self._base_event()
        e1["all_tasks"] = [{"name": "Bake", "assigned": ["Alice"], "required": 2}]
        e2 = self._base_event()
        e2["all_tasks"] = [{"name": "Bake", "assigned": ["Alice", "Bob"], "required": 2}]
        assert event_fingerprint(e1) != event_fingerprint(e2)

    def test_missing_fields_default(self) -> None:
        fp = event_fingerprint({})
        assert fp["title"] is None
        assert fp["my_tasks"] == ()
        assert fp["all_tasks"] == ()
        assert fp["open_tasks_count"] == 0


class TestReadPastEventBlocks:
    def _make_ics(self, tmp_path, vevents: list[str]) -> str:
        body = "BEGIN:VCALENDAR\nVERSION:2.0\n" + "\n".join(vevents) + "\nEND:VCALENDAR\n"
        path = tmp_path / "cal.ics"
        path.write_text(body)
        return str(path)

    def _vevent(self, uid: str, dtstart: str) -> str:
        return f"BEGIN:VEVENT\nUID:{uid}\nDTSTART:{dtstart}\nDTEND:{dtstart}\nEND:VEVENT"

    def test_missing_file_returns_empty(self) -> None:
        assert read_past_event_blocks("/nonexistent/path.ics", datetime.now(UTC), set()) == []

    def test_past_event_returned(self, tmp_path) -> None:
        ics = self._make_ics(tmp_path, [self._vevent("evt-1@x", "20240101T120000Z")])
        now = datetime(2026, 5, 30, tzinfo=UTC)
        result = read_past_event_blocks(ics, now, current_uids=set())
        assert len(result) == 1
        assert "UID:evt-1@x" in result[0]

    def test_future_event_skipped(self, tmp_path) -> None:
        ics = self._make_ics(tmp_path, [self._vevent("evt-future@x", "20270101T120000Z")])
        now = datetime(2026, 5, 30, tzinfo=UTC)
        assert read_past_event_blocks(ics, now, current_uids=set()) == []

    def test_past_event_skipped_if_in_current(self, tmp_path) -> None:
        ics = self._make_ics(tmp_path, [self._vevent("evt-1@x", "20240101T120000Z")])
        now = datetime(2026, 5, 30, tzinfo=UTC)
        # Spond still knows about evt-1, so we drop it from history (will be re-added)
        assert read_past_event_blocks(ics, now, current_uids={"evt-1@x"}) == []

    def test_mix_of_past_and_future(self, tmp_path) -> None:
        ics = self._make_ics(
            tmp_path,
            [
                self._vevent("past-1@x", "20240101T120000Z"),
                self._vevent("past-2@x", "20240601T120000Z"),
                self._vevent("future-1@x", "20270101T120000Z"),
            ],
        )
        now = datetime(2026, 5, 30, tzinfo=UTC)
        result = read_past_event_blocks(ics, now, current_uids=set())
        assert len(result) == 2
        assert any("past-1@x" in b for b in result)
        assert any("past-2@x" in b for b in result)
        assert not any("future-1@x" in b for b in result)

    def test_date_only_dtstart_supported(self, tmp_path) -> None:
        # All-day events have DTSTART:YYYYMMDD (no time)
        vevent = "BEGIN:VEVENT\nUID:allday@x\nDTSTART;VALUE=DATE:20240101\nEND:VEVENT"
        ics = self._make_ics(tmp_path, [vevent])
        now = datetime(2026, 5, 30, tzinfo=UTC)
        result = read_past_event_blocks(ics, now, current_uids=set())
        assert len(result) == 1

    def test_block_without_dtstart_skipped(self, tmp_path) -> None:
        vevent = "BEGIN:VEVENT\nUID:no-date@x\nEND:VEVENT"
        ics = self._make_ics(tmp_path, [vevent])
        result = read_past_event_blocks(ics, datetime.now(UTC), current_uids=set())
        assert result == []
