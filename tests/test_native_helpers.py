"""Tests for the native HA integration's spond_helpers.py.

Uses importlib to load the native module directly, bypassing the APP_DIR
that conftest.py places first in sys.path (which would otherwise resolve
`import spond_helpers` to the AppDaemon version).
"""

import importlib.util
from pathlib import Path

# ── load native module ────────────────────────────────────────────────────────
_NATIVE_DIR = Path(__file__).parent.parent / "custom_components" / "spond_tracker"
_spec = importlib.util.spec_from_file_location(
    "native_spond_helpers", _NATIVE_DIR / "spond_helpers.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

member_canonical = _mod.member_canonical
members_from_events = _mod.members_from_events
dedup_members_by_first_token = _mod.dedup_members_by_first_token
process_raw_events = _mod.process_raw_events


# ── helpers shared across test classes ───────────────────────────────────────


def _make_member(mid: str, first: str, last: str = "") -> dict:
    return {"id": mid, "firstName": first, "lastName": last}


def _make_event(
    ev_id: str,
    member_id: str,
    first: str,
    last: str = "",
    *,
    heading: str = "Practice",
    start: str = "2026-06-10T18:00:00Z",
    end: str = "2026-06-10T20:00:00Z",
    cancelled: bool = False,
    location: str = "",
    address: str = "",
    response: str = "accepted",  # accepted | declined | waitinglist | unanswered | none
    open_tasks: list | None = None,
    assigned_tasks: list | None = None,
) -> dict:
    responses: dict = {
        "acceptedIds": [],
        "declinedIds": [],
        "waitinglistIds": [],
        "unansweredIds": [],
    }
    if response == "accepted":
        responses["acceptedIds"] = [member_id]
    elif response == "declined":
        responses["declinedIds"] = [member_id]
    elif response == "waitinglist":
        responses["waitinglistIds"] = [member_id]
    elif response == "unanswered":
        responses["unansweredIds"] = [member_id]
    # "none" -> not in any list (unknown status)

    return {
        "id": ev_id,
        "heading": heading,
        "startTimestamp": start,
        "endTimestamp": end,
        "cancelled": cancelled,
        "location": {"feature": location, "address": address},
        "behalfOfIds": [member_id],
        "recipients": {"group": {"members": [_make_member(member_id, first, last)]}},
        "responses": responses,
        "tasks": {
            "openTasks": open_tasks or [],
            "assignedTasks": assigned_tasks or [],
        },
    }


def _fresh_state(*canonicals: str) -> tuple:
    """Return (canonical_names, seen_uids, events_per_member, tasks_per_member)."""
    return (
        set(canonicals),
        {c: set() for c in canonicals},
        {c: [] for c in canonicals},
        {c: {} for c in canonicals},
    )


# ── TestMemberCanonical ───────────────────────────────────────────────────────


class TestMemberCanonical:
    def test_simple_first_name(self) -> None:
        assert member_canonical({"firstName": "Sivert"}) == "sivert"

    def test_lowercased(self) -> None:
        assert member_canonical({"firstName": "ANNA"}) == "anna"

    def test_multi_word_first_name_uses_first_token(self) -> None:
        assert member_canonical({"firstName": "Jan Erik"}) == "jan"

    def test_strips_whitespace(self) -> None:
        assert member_canonical({"firstName": "  Lena  "}) == "lena"

    def test_empty_first_name_returns_empty(self) -> None:
        assert member_canonical({"firstName": ""}) == ""

    def test_none_first_name_returns_empty(self) -> None:
        assert member_canonical({"firstName": None}) == ""

    def test_missing_key_returns_empty(self) -> None:
        assert member_canonical({}) == ""

    def test_last_name_ignored(self) -> None:
        assert member_canonical({"firstName": "Erik", "lastName": "Hansen"}) == "erik"


# ── TestMembersFromEvents ─────────────────────────────────────────────────────


class TestMembersFromEvents:
    def test_empty_events_returns_empty(self) -> None:
        assert members_from_events([]) == []

    def test_single_member(self) -> None:
        events = [_make_event("e1", "m1", "Sivert", "Gjendem")]
        result = members_from_events(events)
        assert len(result) == 1
        assert result[0] == {"canonical": "sivert", "display_name": "Sivert Gjendem"}

    def test_same_child_two_events_deduped(self) -> None:
        ev1 = _make_event("e1", "m1a", "Sivert", "Gjendem")
        ev2 = _make_event("e2", "m1b", "Sivert", "Gjendem")
        # Different member IDs but same first name → one canonical
        result = members_from_events([ev1, ev2])
        assert len(result) == 1
        assert result[0]["canonical"] == "sivert"

    def test_two_different_children(self) -> None:
        ev1 = _make_event("e1", "m1", "Sivert", "G")
        ev2 = _make_event("e2", "m2", "Mathias", "G")
        result = members_from_events([ev1, ev2])
        assert {r["canonical"] for r in result} == {"sivert", "mathias"}

    def test_sorted_by_display_name(self) -> None:
        events = [
            _make_event("e1", "m1", "Zoey"),
            _make_event("e2", "m2", "Alice"),
            _make_event("e3", "m3", "Bob"),
        ]
        result = members_from_events(events)
        assert [r["display_name"] for r in result] == ["Alice", "Bob", "Zoey"]

    def test_member_not_in_behalf_of_ids_skipped(self) -> None:
        # If behalfOfIds is empty, no members discovered
        ev = _make_event("e1", "m1", "Sivert")
        ev["behalfOfIds"] = []
        assert members_from_events([ev]) == []

    def test_behalf_id_not_in_group_members_skipped(self) -> None:
        ev = _make_event("e1", "m1", "Sivert")
        ev["behalfOfIds"] = ["unknown-id"]
        assert members_from_events([ev]) == []

    def test_fallback_canonical_from_member_id_when_no_first_name(self) -> None:
        ev = _make_event("e1", "abcdef12", "", "")
        result = members_from_events([ev])
        assert len(result) == 1
        assert result[0]["canonical"] == "abcdef12"[:8].lower()

    def test_display_name_strips_trailing_space_when_no_last_name(self) -> None:
        ev = _make_event("e1", "m1", "Sivert", "")
        result = members_from_events([ev])
        assert result[0]["display_name"] == "Sivert"

    def test_multi_word_first_name_canonical_is_first_token(self) -> None:
        ev = _make_event("e1", "m1", "Jan Erik", "Olsen")
        result = members_from_events([ev])
        assert result[0]["canonical"] == "jan"


# ── TestDedupMembersByFirstToken ──────────────────────────────────────────────


class TestDedupMembersByFirstToken:
    def test_empty_returns_empty(self) -> None:
        assert dedup_members_by_first_token([]) == []

    def test_no_duplicates_unchanged(self) -> None:
        members = [
            {"canonical": "sivert", "display_name": "Sivert G."},
            {"canonical": "mathias", "display_name": "Mathias G."},
        ]
        result = dedup_members_by_first_token(members)
        assert len(result) == 2
        assert {r["canonical"] for r in result} == {"sivert", "mathias"}

    def test_duplicate_collapses_to_first_occurrence(self) -> None:
        members = [
            {"canonical": "mathias", "display_name": "Mathias G."},
            {"canonical": "mathias_g", "display_name": "Mathias G. (2)"},
        ]
        result = dedup_members_by_first_token(members)
        assert len(result) == 1
        assert result[0]["canonical"] == "mathias"
        assert result[0]["display_name"] == "Mathias G."

    def test_multiple_duplicates(self) -> None:
        members = [
            {"canonical": "sivert", "display_name": "Sivert A"},
            {"canonical": "sivert_g", "display_name": "Sivert A (2)"},
            {"canonical": "sivert_extra", "display_name": "Sivert A (3)"},
        ]
        result = dedup_members_by_first_token(members)
        assert len(result) == 1
        assert result[0]["canonical"] == "sivert"

    def test_different_first_tokens_both_kept(self) -> None:
        members = [
            {"canonical": "anna_x", "display_name": "Anna X"},
            {"canonical": "bob_y", "display_name": "Bob Y"},
        ]
        result = dedup_members_by_first_token(members)
        assert {r["canonical"] for r in result} == {"anna", "bob"}

    def test_canonical_rewritten_to_first_token(self) -> None:
        members = [{"canonical": "jan_erik", "display_name": "Jan Erik"}]
        result = dedup_members_by_first_token(members)
        assert result[0]["canonical"] == "jan"

    def test_preserves_order_of_first_occurrences(self) -> None:
        members = [
            {"canonical": "zebra", "display_name": "Z"},
            {"canonical": "alpha", "display_name": "A"},
            {"canonical": "zebra_2", "display_name": "Z2"},
        ]
        result = dedup_members_by_first_token(members)
        assert [r["canonical"] for r in result] == ["zebra", "alpha"]


# ── TestProcessRawEvents ──────────────────────────────────────────────────────


class TestProcessRawEvents:
    """Full integration tests for the inner event-processing loop."""

    # ── status mapping ────────────────────────────────────────────────────────

    def test_accepted_status(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        ev = _make_event("e1", "m1", "Sivert", response="accepted")
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["sivert"][0]["status"] == "accepted"

    def test_declined_status(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        ev = _make_event("e1", "m1", "Sivert", response="declined")
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["sivert"][0]["status"] == "declined"

    def test_waitinglist_status(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        ev = _make_event("e1", "m1", "Sivert", response="waitinglist")
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["sivert"][0]["status"] == "waitinglist"

    def test_unanswered_status(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        ev = _make_event("e1", "m1", "Sivert", response="unanswered")
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["sivert"][0]["status"] == "unanswered"

    def test_unknown_status_when_not_in_any_response_list(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        ev = _make_event("e1", "m1", "Sivert", response="none")
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["sivert"][0]["status"] == "unknown"

    def test_cancelled_event_overrides_response_status(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        # accepted in responses but the event itself is cancelled
        ev = _make_event("e1", "m1", "Sivert", response="accepted", cancelled=True)
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["sivert"][0]["status"] == "cancelled"

    # ── event fields ──────────────────────────────────────────────────────────

    def test_event_fields_populated(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        ev = _make_event(
            "e1",
            "m1",
            "Sivert",
            heading="Training",
            start="2026-07-01T08:00:00Z",
            end="2026-07-01T10:00:00Z",
            location="Hall A",
            address="Main St 1",
        )
        process_raw_events([ev], cn, su, epm, tpm)
        e = epm["sivert"][0]
        assert e["uid"] == "e1"
        assert e["title"] == "Training"
        assert e["start"] == "2026-07-01T08:00:00Z"
        assert e["end"] == "2026-07-01T10:00:00Z"
        assert e["location"] == "Hall A"
        assert e["address"] == "Main St 1"

    def test_empty_events_list(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        process_raw_events([], cn, su, epm, tpm)
        assert epm["sivert"] == []

    # ── member filtering ──────────────────────────────────────────────────────

    def test_member_not_in_canonical_names_skipped(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        ev = _make_event("e1", "m2", "Mathias")  # not tracked
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["sivert"] == []

    def test_member_not_in_group_members_skipped(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        ev = _make_event("e1", "m1", "Sivert")
        ev["behalfOfIds"] = ["unknown-id"]  # not in recipients.group.members
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["sivert"] == []

    def test_two_members_both_tracked(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert", "mathias")
        ev_s = _make_event("e1", "m1", "Sivert")
        ev_m = _make_event("e2", "m2", "Mathias")
        process_raw_events([ev_s, ev_m], cn, su, epm, tpm)
        assert len(epm["sivert"]) == 1
        assert len(epm["mathias"]) == 1

    # ── cross-account / cross-group deduplication ─────────────────────────────

    def test_cross_account_dedup_via_seen_uids(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        ev = _make_event("e1", "m1", "Sivert")
        # Simulate two accounts returning the same event
        process_raw_events([ev], cn, su, epm, tpm)
        process_raw_events([ev], cn, su, epm, tpm)  # second account
        # Must appear only once
        assert len(epm["sivert"]) == 1

    def test_cross_group_dedup_same_event_id_two_member_ids(self) -> None:
        # Same event, member appears in behalfOfIds twice (different group IDs)
        cn, su, epm, tpm = _fresh_state("sivert")
        ev = _make_event("e1", "m1a", "Sivert")
        # Add a second ID for the same person
        ev["behalfOfIds"] = ["m1a", "m1b"]
        ev["recipients"]["group"]["members"].append(_make_member("m1b", "Sivert", "G"))
        ev["responses"]["acceptedIds"] = ["m1a", "m1b"]
        process_raw_events([ev], cn, su, epm, tpm)
        assert len(epm["sivert"]) == 1

    def test_different_events_both_added(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        ev1 = _make_event("e1", "m1", "Sivert")
        ev2 = _make_event("e2", "m1", "Sivert")
        process_raw_events([ev1, ev2], cn, su, epm, tpm)
        assert len(epm["sivert"]) == 2

    # ── tasks ─────────────────────────────────────────────────────────────────

    def _task(self, name: str, member_ids: list, required: int = 0) -> dict:
        return {
            "name": name,
            "assignments": {"memberIds": member_ids, "required": required},
        }

    def test_task_assigned_to_tracked_member(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        task = self._task("Drive", ["m1"], required=1)
        ev = _make_event("e1", "m1", "Sivert", "G", assigned_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        assert "e1::Drive" in tpm["sivert"]
        t = tpm["sivert"]["e1::Drive"]
        assert t["task_name"] == "Drive"
        assert t["required"] == 1
        assert t["assigned_count"] == 1

    def test_task_not_assigned_to_untracked_member(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        task = self._task("Drive", ["m2"], required=1)  # m2 = Mathias, not tracked
        ev = _make_event("e1", "m1", "Sivert")
        ev["recipients"]["group"]["members"].append(_make_member("m2", "Mathias"))
        ev["tasks"]["assignedTasks"] = [task]
        process_raw_events([ev], cn, su, epm, tpm)
        assert tpm["sivert"] == {}

    def test_task_dedup_across_accounts(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        task = self._task("Drive", ["m1"])
        ev = _make_event("e1", "m1", "Sivert", assigned_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        process_raw_events([ev], cn, su, epm, tpm)  # same event from second account
        assert len(tpm["sivert"]) == 1

    def test_co_assignees_populated(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        # Sivert (m1) and Mathias (m2) both assigned to the same task
        task = {"name": "Setup", "assignments": {"memberIds": ["m1", "m2"], "required": 2}}
        ev = _make_event("e1", "m1", "Sivert", "Gjendem", assigned_tasks=[task])
        ev["recipients"]["group"]["members"].append(_make_member("m2", "Mathias", "G"))
        process_raw_events([ev], cn, su, epm, tpm)
        t = tpm["sivert"]["e1::Setup"]
        assert t["co_assignees"] == ["Mathias G"]

    def test_my_tasks_populated_in_event(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        task = self._task("Drive", ["m1"], required=1)
        ev = _make_event("e1", "m1", "Sivert", "G", assigned_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        e = epm["sivert"][0]
        assert len(e["my_tasks"]) == 1
        assert e["my_tasks"][0]["name"] == "Drive"

    def test_my_tasks_excludes_self_from_co_assignees(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        task = {"name": "Setup", "assignments": {"memberIds": ["m1", "m2"], "required": 2}}
        ev = _make_event("e1", "m1", "Sivert", "G", assigned_tasks=[task])
        ev["recipients"]["group"]["members"].append(_make_member("m2", "Anna", "P"))
        process_raw_events([ev], cn, su, epm, tpm)
        e = epm["sivert"][0]
        my_task = e["my_tasks"][0]
        assert "Sivert G" not in my_task["co_assignees"]
        assert "Anna P" in my_task["co_assignees"]

    def test_open_task_counted(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        # Task needs 2 people but only 1 assigned → open
        task = self._task("Setup", ["m1"], required=2)
        ev = _make_event("e1", "m1", "Sivert", assigned_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["sivert"][0]["open_tasks_count"] == 1

    def test_all_tasks_detail_includes_non_my_tasks(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        # m2=Mathias assigned to a task; Sivert is only behalfOf, not assigned
        task = self._task("Cook", ["m2"], required=1)
        ev = _make_event("e1", "m1", "Sivert")
        ev["recipients"]["group"]["members"].append(_make_member("m2", "Mathias", "G"))
        ev["tasks"]["assignedTasks"] = [task]
        process_raw_events([ev], cn, su, epm, tpm)
        e = epm["sivert"][0]
        assert e["my_tasks"] == []
        assert len(e["all_tasks"]) == 1
        assert e["all_tasks"][0]["name"] == "Cook"

    def test_cancelled_task_event_field_set(self) -> None:
        cn, su, epm, tpm = _fresh_state("sivert")
        task = self._task("Drive", ["m1"])
        ev = _make_event("e1", "m1", "Sivert", assigned_tasks=[task], cancelled=True)
        process_raw_events([ev], cn, su, epm, tpm)
        t = tpm["sivert"]["e1::Drive"]
        assert t["cancelled"] is True
