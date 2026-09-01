"""Pure-function helpers for Spond Tracker.

Nothing here touches HA or Spond directly.
"""

import hashlib
from datetime import UTC, datetime, time, timedelta

# A member sits in `unansweredIds` both when they genuinely have not replied and
# when the invitation has not gone out at all. Only the first is actionable, so
# the second gets a status of its own.
STATUS_NOT_INVITED = "not_invited"


def event_fingerprint(e: dict) -> dict:
    """Subset of event fields for change detection."""
    my_task_names = tuple(
        sorted(t.get("name") if isinstance(t, dict) else t for t in (e.get("my_tasks") or []))
    )
    my_task_states = tuple(
        sorted(
            f"{t.get('name')}:{t.get('status')}"
            for t in (e.get("my_tasks") or [])
            if isinstance(t, dict)
        )
    )
    all_task_names = tuple(
        sorted(
            f"{t.get('name')}:{len(t.get('assigned') or [])}/{t.get('required', 0)}"
            if isinstance(t, dict)
            else t
            for t in (e.get("all_tasks") or [])
        )
    )
    return {
        "title": e.get("title"),
        "start": e.get("start"),
        "end": e.get("end"),
        "location": e.get("location"),
        "status": e.get("status"),
        # Flips the moment the invitation is sent, which is the first point at
        # which answering is even possible.
        "invited": e.get("invited", True),
        "my_tasks": my_task_names,
        "my_task_states": my_task_states,
        "all_tasks": all_task_names,
        "open_tasks_count": e.get("open_tasks_count", 0),
    }


def stable_uid_for(spond_uid: str, canonical: str) -> str:
    h = hashlib.md5(f"{spond_uid}-{canonical}".encode()).hexdigest()
    return f"{h}@spond-sync.local"


def member_canonical(mem: dict) -> str:
    """First-name first-token, lowercased — the stable identity key for a member dict."""
    first_name = (mem.get("firstName") or "").strip()
    return first_name.split()[0].lower() if first_name else ""


def device_name_for(display_name: str) -> str:
    """Device name for a member: "Spond - Alice".

    Entities use has_entity_name, so the device name is the prefix of every
    friendly name this integration produces. A bare person's name reads
    ambiguously next to the calendars and sensors other integrations create for
    the same person, so the source is named first.

    Only the first name is used. Members are already deduplicated by first name
    (see member_canonical), so first names are unique within one config entry by
    construction, and the surname only makes every entity name longer.
    """
    first = (display_name or "").strip().split()
    return f"Spond - {first[0]}" if first else "Spond"


TASK_STATES = ("accepted", "declined", "unanswered")


def _assignee_ids(value) -> list[str]:
    """Normalize a Spond task response list to plain member ids.

    Spond is inconsistent here: `accepted` and `declined` arrive as
    ``[{"id": ..., "message": ...}]`` while `unanswered` is a bare list of id
    strings. Both shapes mean the same thing.
    """
    ids: list[str] = []
    for item in value or []:
        ident = item.get("id") if isinstance(item, dict) else item
        if ident:
            ids.append(ident)
    return ids


def people_in_event(ev: dict) -> dict[str, dict]:
    """Map every member id appearing in an event to {canonical, display_name}.

    Spond splits the people in an event across separate lists: the players sit
    in ``recipients.group.members`` while the adults who answer for them sit in
    ``recipients.profiles`` (with ``recipients.guardians`` and a per-player
    ``guardians`` list carrying the same shape). Task assignees are drawn from
    all of them, so a lookup that only reads group members cannot resolve an
    adult at all — which is why tasks have to be matched through this map.
    """
    recipients = ev.get("recipients") or {}
    group = recipients.get("group") or {}
    people: dict[str, dict] = {}

    def _add(record: dict) -> None:
        ident = record.get("id")
        if not ident or ident in people:
            return
        first = (record.get("firstName") or "").strip()
        if not first:
            return
        last = (record.get("lastName") or "").strip()
        people[ident] = {
            "canonical": first.split()[0].lower(),
            "display_name": f"{first} {last}".strip(),
        }

    for member in group.get("members") or []:
        _add(member)
        for guardian in member.get("guardians") or []:
            _add(guardian)
    for profile in recipients.get("profiles") or []:
        _add(profile)
    for guardian in recipients.get("guardians") or []:
        _add(guardian)
    return people


def invitation_pending(ev: dict, now: datetime) -> bool:
    """True while an event's invitation has not been sent out yet.

    Spond schedules invitations: an event can sit in the calendar for weeks
    before anyone is asked to reply, and ``inviteTime`` says when the asking
    happens. Spond drops the field once the invitation goes out, so its mere
    presence would almost do — but comparing against ``now`` is correct under
    either mechanism, and lets an event leave the pending state on its own
    between two polls without Spond having to change anything.
    """
    raw = ev.get("inviteTime")
    if not raw or not isinstance(raw, str):
        return False
    try:
        invite_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    if invite_at.tzinfo is None:
        invite_at = invite_at.replace(tzinfo=UTC)
    return invite_at > now


def task_view(task: dict, people: dict[str, dict]) -> dict:
    """Normalize one raw Spond task into the shape the entities render.

    Spond has two kinds. An OPEN task offers ``limit`` slots that anyone may
    take, with ``remaining`` still free. An ASSIGNED task is handed to named
    people who each accept, decline, or leave it unanswered. Neither carries
    the ``assignments.memberIds`` / ``required`` pair this integration used to
    look for, which is why no task ever reached an entity.
    """
    by_state = {state: _assignee_ids(task.get(state)) for state in TASK_STATES}
    accepted = by_state["accepted"]
    task_type = (task.get("type") or "").upper() or "OPEN"
    remaining = task.get("remaining")

    if task_type == "OPEN":
        required = task.get("limit") or 0
        is_open = remaining > 0 if isinstance(remaining, int) else len(accepted) < required
    else:
        # An assigned task has no slot count — it is open until someone accepts.
        required = 0
        is_open = not accepted

    return {
        "id": task.get("id"),
        "name": task.get("name", "?"),
        "description": task.get("description") or "",
        "type": task_type,
        "adults_only": bool(task.get("adultsOnly")),
        "required": required,
        "remaining": remaining if isinstance(remaining, int) else None,
        "is_open": is_open,
        "by_state": by_state,
        "assigned": [people[i]["display_name"] for i in accepted if i in people],
    }


def other_assignee_names(ids: list[str], self_id: str, people: dict[str, dict]) -> list[str]:
    """Display names of everyone signed up for a task except the member itself."""
    return [people[i]["display_name"] for i in ids if i != self_id and i in people]


def members_from_events(events: list[dict]) -> list[dict]:
    """Discover unique trackable members from a list of raw Spond events.

    A person is trackable when they appear in an event's ``behalfOfIds`` — the
    members the signed-in account answers for. Those ids are resolved through
    :func:`people_in_event`, so adults who exist only in ``recipients.profiles``
    are discovered too, not just the players on the group roster.

    Deduplicates by first-name canonical, so the same child appearing in
    multiple groups collapses to one entry. Returns list[{canonical,
    display_name}] sorted by display_name. No Spond member IDs are stored:
    Spond issues a fresh id per group, and per event for adults, so an id is
    never a stable identity across the whole account.
    """
    persons: dict[str, dict] = {}
    for ev in events:
        people = people_in_event(ev)
        for mid in ev.get("behalfOfIds") or []:
            person = people.get(mid)
            if person and person["canonical"] not in persons:
                persons[person["canonical"]] = dict(person)
    return sorted(persons.values(), key=lambda m: m["display_name"])


def dedup_members_by_first_token(members: list[dict]) -> list[dict]:
    """Collapse members whose canonical shares the same first underscore-token.

    Used during v1→v2 migration when the old code stored separate entries for
    the same child across groups (e.g. "bob" and "bob_g" both collapse
    to "bob").  The first occurrence's display_name is kept.
    """
    seen: set[str] = set()
    result: list[dict] = []
    for m in members:
        first_token = m["canonical"].split("_")[0]
        if first_token not in seen:
            seen.add(first_token)
            result.append({"canonical": first_token, "display_name": m["display_name"]})
    return result


def process_raw_events(
    raw_events: list[dict],
    canonical_names: set[str],
    seen_uids: dict[str, set[str]],
    events_per_member: dict[str, list[dict]],
    tasks_per_member: dict[str, dict[str, dict]],
    account: str | None = None,
    now: datetime | None = None,
) -> None:
    """Process one account's raw Spond events into the shared per-member dicts.

    Mutates seen_uids, events_per_member, and tasks_per_member in place.
    Call once per account; seen_uids provides cross-account deduplication.
    `account` records which login a task came from, since responding to it has
    to go back through that same account.

    Every match here is made on member id, never on a name. ``behalfOfIds``
    states exactly which member records this account answers for in this event,
    so a stranger who happens to share a first name with a tracked member can
    never pick up their tasks — a real hazard, since one group can hold three
    people with the same first name.

    `now` decides which invitations still count as unsent; it is injected so
    tests can pin it.
    """
    now = now or datetime.now(UTC)
    for ev in raw_events:
        ev_id = ev.get("id")
        people = people_in_event(ev)
        behalfof_ids = ev.get("behalfOfIds") or []
        our_ids = {mid for mid in behalfof_ids if mid in people}

        tasks_block = ev.get("tasks") or {}
        tasks = [
            task_view(t, people)
            for t in (tasks_block.get("openTasks") or []) + (tasks_block.get("assignedTasks") or [])
        ]

        cancelled = bool(ev.get("cancelled"))
        pending_invite = invitation_pending(ev, now)
        invite_time = ev.get("inviteTime") if pending_invite else None
        location = (ev.get("location") or {}).get("feature") or ""
        address = (ev.get("location") or {}).get("address") or ""

        # --- Tasks: an assignee is ours only if its id is in behalfOfIds ---
        for task in tasks:
            for state in TASK_STATES:
                for assignee_id in task["by_state"][state]:
                    if assignee_id not in our_ids:
                        continue
                    canonical = people[assignee_id]["canonical"]
                    if canonical not in canonical_names or canonical not in tasks_per_member:
                        continue
                    task_uid_key = f"{ev_id}::{task['name']}"
                    if task_uid_key in tasks_per_member[canonical]:
                        continue
                    tasks_per_member[canonical][task_uid_key] = {
                        "task_uid_key": task_uid_key,
                        "event_uid": ev_id,
                        "task_id": task["id"],
                        # The assignment id is event-scoped and is what the
                        # respond endpoint addresses — not the profile id.
                        "member_id": assignee_id,
                        "account": account,
                        "task_name": task["name"],
                        "task_type": task["type"],
                        "status": state,
                        "adults_only": task["adults_only"],
                        "event_title": ev.get("heading", "?"),
                        "start": ev.get("startTimestamp"),
                        "end": ev.get("endTimestamp"),
                        "location": location,
                        "address": address,
                        "required": task["required"],
                        "assigned_count": len(task["by_state"]["accepted"]),
                        "co_assignees": other_assignee_names(
                            task["by_state"]["accepted"], assignee_id, people
                        ),
                        "cancelled": cancelled,
                        "invited": not pending_invite,
                        "invite_time": invite_time,
                    }

        # --- Events: behalfOfIds are member ids already, so no name matching ---
        responses = ev.get("responses") or {}
        accepted_ids = set(responses.get("acceptedIds") or [])
        declined_ids = set(responses.get("declinedIds") or [])
        waiting_ids = set(responses.get("waitinglistIds") or [])
        unanswered_ids = set(responses.get("unansweredIds") or [])

        for mem_id in behalfof_ids:
            person = people.get(mem_id)
            if not person:
                continue
            canonical = person["canonical"]
            if canonical not in canonical_names or canonical not in seen_uids:
                continue
            if ev_id in seen_uids[canonical]:
                continue  # already seen from another account or group
            seen_uids[canonical].add(ev_id)

            if cancelled:
                status = "cancelled"
            elif mem_id in accepted_ids:
                status = "accepted"
            elif mem_id in declined_ids:
                status = "declined"
            elif mem_id in waiting_ids:
                status = "waitinglist"
            elif pending_invite:
                # Spond parks everyone in `unansweredIds` until the invitation
                # is sent, so without this branch a not-yet-invited event is
                # indistinguishable from one the member is ignoring.
                status = STATUS_NOT_INVITED
            elif mem_id in unanswered_ids:
                status = "unanswered"
            else:
                status = "unknown"

            my_tasks: list[dict] = []
            all_tasks_detail: list[dict] = []
            open_tasks_count = 0

            for task in tasks:
                my_state = next(
                    (s for s in TASK_STATES if mem_id in task["by_state"][s]),
                    None,
                )
                if my_state:
                    my_tasks.append(
                        {
                            "name": task["name"],
                            "status": my_state,
                            "co_assignees": other_assignee_names(
                                task["by_state"]["accepted"], mem_id, people
                            ),
                            "required": task["required"],
                            "assigned_count": len(task["by_state"]["accepted"]),
                        }
                    )
                if task["is_open"]:
                    open_tasks_count += 1
                all_tasks_detail.append(
                    {
                        "name": task["name"],
                        "assigned": task["assigned"],
                        "required": task["required"],
                        "is_open": task["is_open"],
                        "adults_only": task["adults_only"],
                    }
                )

            if canonical not in events_per_member:
                continue

            # Spond adds task assignees to `behalfOfIds` without inviting them
            # to the event itself, which is exactly what leaves `status` at
            # "unknown": the member is present only because a task points at
            # them. Once every one of those tasks is declined they have no role
            # left, so the event should not linger on their calendar. Guarded on
            # the event actually carrying response data, so an API hiccup that
            # strips `responses` degrades to the old behaviour rather than
            # silently emptying every calendar.
            has_responses = bool(accepted_ids or declined_ids or waiting_ids or unanswered_ids)
            if (
                status == "unknown"
                and has_responses
                and not any(t["status"] != "declined" for t in my_tasks)
            ):
                continue

            events_per_member[canonical].append(
                {
                    "uid": ev_id,
                    "title": ev.get("heading", "Spond"),
                    "start": ev.get("startTimestamp"),
                    "end": ev.get("endTimestamp"),
                    "location": location,
                    "address": address,
                    "status": status,
                    "invited": not pending_invite,
                    "invite_time": invite_time,
                    "my_tasks": my_tasks,
                    "all_tasks": all_tasks_detail,
                    "open_tasks_count": open_tasks_count,
                }
            )


def parse_clock(value: object, fallback: str) -> time:
    """Parse an "HH:MM" / "HH:MM:SS" option into a time, falling back on junk."""
    for candidate in (value, fallback):
        if isinstance(candidate, str) and candidate:
            parts = candidate.split(":")
            try:
                hour, minute = int(parts[0]), int(parts[1])
                second = int(parts[2]) if len(parts) > 2 else 0
                return time(hour, minute, second)
            except (ValueError, IndexError):
                continue
    return time(0, 0)


def in_quiet_hours(now_t: time, start: time, end: time) -> bool:
    """Whether `now_t` falls in the window, which may wrap past midnight."""
    if start == end:
        return False
    if start < end:
        return start <= now_t < end
    return now_t >= start or now_t < end


def next_poll_minutes(
    now: datetime,
    day_minutes: int,
    night_minutes: int,
    start: time,
    end: time,
) -> int:
    """How long to wait before the next poll, given the time of day.

    Nothing observable happens overnight — no invitation goes out and no event
    starts — so the interval can stretch. It is deliberately not allowed to
    stretch *past* the end of the quiet window: the first daytime poll should
    land as the window closes, so anything reading Spond data over breakfast
    sees a fresh picture rather than one from hours earlier.
    """
    # A night interval that is absent, zero, or no longer than the daytime one
    # has nothing to offer, so the whole feature stays out of the way.
    if night_minutes <= 0 or night_minutes <= day_minutes:
        return day_minutes
    if not in_quiet_hours(now.time(), start, end):
        return day_minutes

    end_dt = now.replace(hour=end.hour, minute=end.minute, second=end.second, microsecond=0)
    if end_dt <= now:
        end_dt += timedelta(days=1)
    minutes_left = max(1, round((end_dt - now).total_seconds() / 60))
    return min(night_minutes, minutes_left)
