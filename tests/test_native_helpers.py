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
people_in_event = _mod.people_in_event
task_view = _mod.task_view
event_fingerprint = _mod.event_fingerprint


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
        assert member_canonical({"firstName": "Alice"}) == "alice"

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
        events = [_make_event("e1", "m1", "Alice", "Smith")]
        result = members_from_events(events)
        assert len(result) == 1
        assert result[0] == {"canonical": "alice", "display_name": "Alice Smith"}

    def test_same_child_two_events_deduped(self) -> None:
        ev1 = _make_event("e1", "m1a", "Alice", "Smith")
        ev2 = _make_event("e2", "m1b", "Alice", "Smith")
        # Different member IDs but same first name → one canonical
        result = members_from_events([ev1, ev2])
        assert len(result) == 1
        assert result[0]["canonical"] == "alice"

    def test_two_different_children(self) -> None:
        ev1 = _make_event("e1", "m1", "Alice", "G")
        ev2 = _make_event("e2", "m2", "Bob", "G")
        result = members_from_events([ev1, ev2])
        assert {r["canonical"] for r in result} == {"alice", "bob"}

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
        ev = _make_event("e1", "m1", "Alice")
        ev["behalfOfIds"] = []
        assert members_from_events([ev]) == []

    def test_behalf_id_not_in_group_members_skipped(self) -> None:
        ev = _make_event("e1", "m1", "Alice")
        ev["behalfOfIds"] = ["unknown-id"]
        assert members_from_events([ev]) == []

    def test_member_without_first_name_is_skipped(self) -> None:
        """A nameless member cannot be shown or matched, so it is not offered."""
        ev = _make_event("e1", "abcdef12", "", "")
        assert members_from_events([ev]) == []

    def test_adult_found_via_recipients_profiles(self) -> None:
        """Adults live in recipients.profiles, not on the group roster."""
        ev = _make_event("e1", "m1", "Alice", "Smith")
        ev["recipients"]["profiles"] = [
            {"id": "p1", "firstName": "Carol", "lastName": "Smith", "profileId": "prof-1"}
        ]
        ev["behalfOfIds"] = ["m1", "p1"]
        result = members_from_events([ev])
        assert [m["canonical"] for m in result] == ["alice", "carol"]

    def test_display_name_strips_trailing_space_when_no_last_name(self) -> None:
        ev = _make_event("e1", "m1", "Alice", "")
        result = members_from_events([ev])
        assert result[0]["display_name"] == "Alice"

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
            {"canonical": "alice", "display_name": "Alice G."},
            {"canonical": "bob", "display_name": "Bob G."},
        ]
        result = dedup_members_by_first_token(members)
        assert len(result) == 2
        assert {r["canonical"] for r in result} == {"alice", "bob"}

    def test_duplicate_collapses_to_first_occurrence(self) -> None:
        members = [
            {"canonical": "bob", "display_name": "Bob G."},
            {"canonical": "bob_g", "display_name": "Bob G. (2)"},
        ]
        result = dedup_members_by_first_token(members)
        assert len(result) == 1
        assert result[0]["canonical"] == "bob"
        assert result[0]["display_name"] == "Bob G."

    def test_multiple_duplicates(self) -> None:
        members = [
            {"canonical": "alice", "display_name": "Alice A"},
            {"canonical": "alice_g", "display_name": "Alice A (2)"},
            {"canonical": "alice_extra", "display_name": "Alice A (3)"},
        ]
        result = dedup_members_by_first_token(members)
        assert len(result) == 1
        assert result[0]["canonical"] == "alice"

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
        cn, su, epm, tpm = _fresh_state("alice")
        ev = _make_event("e1", "m1", "Alice", response="accepted")
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["alice"][0]["status"] == "accepted"

    def test_declined_status(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        ev = _make_event("e1", "m1", "Alice", response="declined")
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["alice"][0]["status"] == "declined"

    def test_waitinglist_status(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        ev = _make_event("e1", "m1", "Alice", response="waitinglist")
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["alice"][0]["status"] == "waitinglist"

    def test_unanswered_status(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        ev = _make_event("e1", "m1", "Alice", response="unanswered")
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["alice"][0]["status"] == "unanswered"

    def test_unknown_status_when_not_in_any_response_list(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        ev = _make_event("e1", "m1", "Alice", response="none")
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["alice"][0]["status"] == "unknown"

    def test_cancelled_event_overrides_response_status(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        # accepted in responses but the event itself is cancelled
        ev = _make_event("e1", "m1", "Alice", response="accepted", cancelled=True)
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["alice"][0]["status"] == "cancelled"

    # ── event fields ──────────────────────────────────────────────────────────

    def test_event_fields_populated(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        ev = _make_event(
            "e1",
            "m1",
            "Alice",
            heading="Training",
            start="2026-07-01T08:00:00Z",
            end="2026-07-01T10:00:00Z",
            location="Hall A",
            address="Main St 1",
        )
        process_raw_events([ev], cn, su, epm, tpm)
        e = epm["alice"][0]
        assert e["uid"] == "e1"
        assert e["title"] == "Training"
        assert e["start"] == "2026-07-01T08:00:00Z"
        assert e["end"] == "2026-07-01T10:00:00Z"
        assert e["location"] == "Hall A"
        assert e["address"] == "Main St 1"

    def test_empty_events_list(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        process_raw_events([], cn, su, epm, tpm)
        assert epm["alice"] == []

    # ── member filtering ──────────────────────────────────────────────────────

    def test_member_not_in_canonical_names_skipped(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        ev = _make_event("e1", "m2", "Bob")  # not tracked
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["alice"] == []

    def test_member_not_in_group_members_skipped(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        ev = _make_event("e1", "m1", "Alice")
        ev["behalfOfIds"] = ["unknown-id"]  # not in recipients.group.members
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["alice"] == []

    def test_two_members_both_tracked(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice", "bob")
        ev_s = _make_event("e1", "m1", "Alice")
        ev_m = _make_event("e2", "m2", "Bob")
        process_raw_events([ev_s, ev_m], cn, su, epm, tpm)
        assert len(epm["alice"]) == 1
        assert len(epm["bob"]) == 1

    # ── cross-account / cross-group deduplication ─────────────────────────────

    def test_cross_account_dedup_via_seen_uids(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        ev = _make_event("e1", "m1", "Alice")
        # Simulate two accounts returning the same event
        process_raw_events([ev], cn, su, epm, tpm)
        process_raw_events([ev], cn, su, epm, tpm)  # second account
        # Must appear only once
        assert len(epm["alice"]) == 1

    def test_cross_group_dedup_same_event_id_two_member_ids(self) -> None:
        # Same event, member appears in behalfOfIds twice (different group IDs)
        cn, su, epm, tpm = _fresh_state("alice")
        ev = _make_event("e1", "m1a", "Alice")
        # Add a second ID for the same person
        ev["behalfOfIds"] = ["m1a", "m1b"]
        ev["recipients"]["group"]["members"].append(_make_member("m1b", "Alice", "G"))
        ev["responses"]["acceptedIds"] = ["m1a", "m1b"]
        process_raw_events([ev], cn, su, epm, tpm)
        assert len(epm["alice"]) == 1

    def test_different_events_both_added(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        ev1 = _make_event("e1", "m1", "Alice")
        ev2 = _make_event("e2", "m1", "Alice")
        process_raw_events([ev1, ev2], cn, su, epm, tpm)
        assert len(epm["alice"]) == 2

    # ── tasks ─────────────────────────────────────────────────────────────────

    def _open_task(self, name: str, accepted: list, limit: int = 1) -> dict:
        """An OPEN task: `limit` slots, anyone may sign up. Real Spond shape."""
        return {
            "id": f"t-{name}",
            "name": name,
            "type": "OPEN",
            "adultsOnly": False,
            "limit": limit,
            "remaining": max(limit - len(accepted), 0),
            "accepted": [{"id": i} for i in accepted],
            "declined": [],
            "unanswered": [],
        }

    def _assigned_task(
        self,
        name: str,
        accepted: list | None = None,
        declined: list | None = None,
        unanswered: list | None = None,
    ) -> dict:
        """An ASSIGNED task: named people accept, decline or stay silent."""
        return {
            "id": f"t-{name}",
            "name": name,
            "type": "ASSIGNED",
            "adultsOnly": True,
            "accepted": [{"id": i} for i in accepted or []],
            "declined": [{"id": i} for i in declined or []],
            "unanswered": list(unanswered or []),
        }

    def test_open_task_accepted_by_tracked_member(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._open_task("Drive", ["m1"], limit=1)
        ev = _make_event("e1", "m1", "Alice", "G", open_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        t = tpm["alice"]["e1::Drive"]
        assert t["task_name"] == "Drive"
        assert t["status"] == "accepted"
        assert t["task_type"] == "OPEN"
        assert t["required"] == 1
        assert t["assigned_count"] == 1

    def test_assigned_task_unanswered_is_still_tracked(self) -> None:
        """The whole point of the tasks sensor: what has not been answered."""
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._assigned_task("Iskjorer", unanswered=["m1"])
        ev = _make_event("e1", "m1", "Alice", "G", assigned_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        t = tpm["alice"]["e1::Iskjorer"]
        assert t["status"] == "unanswered"
        assert t["task_type"] == "ASSIGNED"
        assert t["adults_only"] is True

    def test_declined_task_kept_with_status(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._assigned_task("Kiosk", declined=["m1"])
        ev = _make_event("e1", "m1", "Alice", "G", assigned_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        assert tpm["alice"]["e1::Kiosk"]["status"] == "declined"

    def test_task_of_stranger_sharing_first_name_is_ignored(self) -> None:
        """A group can hold three people called Mathias — names must not match."""
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._open_task("Drive", ["m2"], limit=1)
        ev = _make_event("e1", "m1", "Alice", "Smith", open_tasks=[task])
        # Same first name, different person, not in behalfOfIds
        ev["recipients"]["group"]["members"].append(_make_member("m2", "Alice", "Jones"))
        process_raw_events([ev], cn, su, epm, tpm)
        assert tpm["alice"] == {}
        assert epm["alice"][0]["my_tasks"] == []

    def test_task_assigned_to_adult_resolved_via_profiles(self) -> None:
        """The adult who answers for a player is not on the group roster."""
        cn, su, epm, tpm = _fresh_state("carol")
        task = self._assigned_task("Iskjorer", unanswered=["p1"])
        ev = _make_event("e1", "m1", "Alice", "Smith", assigned_tasks=[task])
        ev["recipients"]["profiles"] = [
            {"id": "p1", "firstName": "Carol", "lastName": "Smith", "profileId": "prof-1"}
        ]
        ev["behalfOfIds"] = ["m1", "p1"]
        process_raw_events([ev], cn, su, epm, tpm)
        assert tpm["carol"]["e1::Iskjorer"]["status"] == "unanswered"

    def test_task_dedup_across_accounts(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._open_task("Drive", ["m1"])
        ev = _make_event("e1", "m1", "Alice", open_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        process_raw_events([ev], cn, su, epm, tpm)  # same event from second account
        assert len(tpm["alice"]) == 1

    def test_co_assignees_use_full_name(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._open_task("Setup", ["m1", "m2"], limit=2)
        ev = _make_event("e1", "m1", "Alice", "Smith", open_tasks=[task])
        ev["recipients"]["group"]["members"].append(_make_member("m2", "Bob", "Tingeidet Jones"))
        process_raw_events([ev], cn, su, epm, tpm)
        t = tpm["alice"]["e1::Setup"]
        assert t["co_assignees"] == ["Bob Tingeidet Jones"]

    def test_my_tasks_populated_in_event(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._open_task("Drive", ["m1"], limit=1)
        ev = _make_event("e1", "m1", "Alice", "G", open_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        my_task = epm["alice"][0]["my_tasks"][0]
        assert my_task["name"] == "Drive"
        assert my_task["status"] == "accepted"

    def test_my_tasks_excludes_self_from_co_assignees(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._open_task("Setup", ["m1", "m2"], limit=2)
        ev = _make_event("e1", "m1", "Alice", "G", open_tasks=[task])
        ev["recipients"]["group"]["members"].append(_make_member("m2", "Anna", "P"))
        process_raw_events([ev], cn, su, epm, tpm)
        my_task = epm["alice"][0]["my_tasks"][0]
        assert my_task["co_assignees"] == ["Anna P"]

    def test_open_task_with_free_slot_counted(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._open_task("Setup", ["m1"], limit=2)  # 2 slots, 1 taken
        ev = _make_event("e1", "m1", "Alice", open_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["alice"][0]["open_tasks_count"] == 1

    def test_assigned_task_open_until_someone_accepts(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._assigned_task("Iskjorer", unanswered=["m1", "m2"])
        ev = _make_event("e1", "m1", "Alice", assigned_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        assert epm["alice"][0]["open_tasks_count"] == 1
        assert epm["alice"][0]["all_tasks"][0]["is_open"] is True

    def test_all_tasks_detail_includes_non_my_tasks(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._open_task("Cook", ["m2"], limit=1)
        ev = _make_event("e1", "m1", "Alice", open_tasks=[task])
        ev["recipients"]["group"]["members"].append(_make_member("m2", "Bob", "G"))
        process_raw_events([ev], cn, su, epm, tpm)
        e = epm["alice"][0]
        assert e["my_tasks"] == []
        assert len(e["all_tasks"]) == 1
        assert e["all_tasks"][0]["name"] == "Cook"
        assert e["all_tasks"][0]["assigned"] == ["Bob G"]

    def test_task_carries_ids_needed_to_answer_it(self) -> None:
        """Responding needs the task id, the assignment id and the account."""
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._assigned_task("Drive", unanswered=["m1"])
        ev = _make_event("e1", "m1", "Alice", "G", assigned_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm, account="user@example.com")
        t = tpm["alice"]["e1::Drive"]
        assert t["task_id"] == "t-Drive"
        assert t["member_id"] == "m1"
        assert t["account"] == "user@example.com"

    def test_account_defaults_to_none(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._assigned_task("Drive", unanswered=["m1"])
        ev = _make_event("e1", "m1", "Alice", "G", assigned_tasks=[task])
        process_raw_events([ev], cn, su, epm, tpm)
        assert tpm["alice"]["e1::Drive"]["account"] is None

    def test_cancelled_task_event_field_set(self) -> None:
        cn, su, epm, tpm = _fresh_state("alice")
        task = self._open_task("Drive", ["m1"])
        ev = _make_event("e1", "m1", "Alice", open_tasks=[task], cancelled=True)
        process_raw_events([ev], cn, su, epm, tpm)
        assert tpm["alice"]["e1::Drive"]["cancelled"] is True


# ── TestPeopleInEvent ────────────────────────────────────────────────────────


class TestPeopleInEvent:
    def test_collects_players_guardians_and_profiles(self) -> None:
        ev = {
            "recipients": {
                "group": {
                    "members": [
                        {
                            "id": "m1",
                            "firstName": "Alice",
                            "lastName": "Smith",
                            "guardians": [{"id": "g1", "firstName": "Carol", "lastName": "Smith"}],
                        }
                    ]
                },
                "profiles": [{"id": "p1", "firstName": "Dave", "lastName": "Smith"}],
                "guardians": [{"id": "g2", "firstName": "Erik", "lastName": "Smith"}],
            }
        }
        people = people_in_event(ev)
        assert set(people) == {"m1", "g1", "p1", "g2"}
        assert people["p1"] == {"canonical": "dave", "display_name": "Dave Smith"}

    def test_skips_records_without_a_first_name(self) -> None:
        ev = {"recipients": {"group": {"members": [{"id": "m1", "lastName": "Smith"}]}}}
        assert people_in_event(ev) == {}

    def test_handles_missing_recipients(self) -> None:
        assert people_in_event({}) == {}


# ── TestTaskView ─────────────────────────────────────────────────────────────


class TestTaskView:
    def test_open_task_slots(self) -> None:
        task = {
            "name": "Kiosk",
            "type": "OPEN",
            "limit": 2,
            "remaining": 1,
            "accepted": [{"id": "m1"}],
        }
        view = task_view(task, {"m1": {"canonical": "alice", "display_name": "Alice Smith"}})
        assert view["required"] == 2
        assert view["is_open"] is True
        assert view["assigned"] == ["Alice Smith"]

    def test_open_task_full(self) -> None:
        task = {
            "name": "Kiosk",
            "type": "OPEN",
            "limit": 1,
            "remaining": 0,
            "accepted": [{"id": "m1"}],
        }
        assert task_view(task, {})["is_open"] is False

    def test_assigned_task_open_until_accepted(self) -> None:
        task = {"name": "Drive", "type": "ASSIGNED", "unanswered": ["m1", "m2"]}
        view = task_view(task, {})
        assert view["is_open"] is True
        assert view["required"] == 0
        assert view["by_state"]["unanswered"] == ["m1", "m2"]

    def test_assigned_task_closed_once_accepted(self) -> None:
        task = {
            "name": "Drive",
            "type": "ASSIGNED",
            "accepted": [{"id": "m1"}],
            "unanswered": ["m2"],
        }
        assert task_view(task, {})["is_open"] is False

    def test_mixed_id_shapes_are_normalized(self) -> None:
        """accepted/declined arrive as dicts, unanswered as bare strings."""
        task = {
            "name": "Drive",
            "type": "ASSIGNED",
            "accepted": [{"id": "a1"}],
            "declined": [{"id": "d1", "message": "busy"}],
            "unanswered": ["u1"],
        }
        view = task_view(task, {})
        assert view["by_state"] == {
            "accepted": ["a1"],
            "declined": ["d1"],
            "unanswered": ["u1"],
        }

    def test_missing_remaining_falls_back_to_counting(self) -> None:
        task = {"name": "Kiosk", "type": "OPEN", "limit": 2, "accepted": [{"id": "m1"}]}
        assert task_view(task, {})["is_open"] is True


# ── TestFingerprintTaskStatus ────────────────────────────────────────────────


class TestFingerprintTaskStatus:
    def test_status_change_shows_up_in_fingerprint(self) -> None:
        """Accepting a task must register as a change, not pass unnoticed."""
        before = event_fingerprint({"my_tasks": [{"name": "Drive", "status": "unanswered"}]})
        after = event_fingerprint({"my_tasks": [{"name": "Drive", "status": "accepted"}]})
        assert before["my_tasks"] == after["my_tasks"]
        assert before["my_task_states"] != after["my_task_states"]
