"""Pure-function helpers for Spond Tracker.

Nothing here touches HA or Spond directly.
"""

import hashlib


def event_fingerprint(e: dict) -> dict:
    """Subset of event fields for change detection."""
    my_task_names = tuple(
        sorted(t.get("name") if isinstance(t, dict) else t for t in (e.get("my_tasks") or []))
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
        "my_tasks": my_task_names,
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


def members_from_events(events: list[dict]) -> list[dict]:
    """Discover unique trackable members from a list of raw Spond events.

    Deduplicates by first-name canonical, so the same child appearing in
    multiple groups collapses to one entry.  Returns list[{canonical,
    display_name}] sorted by display_name.  No Spond member IDs are stored.
    """
    persons: dict[str, dict] = {}
    for ev in events:
        recipients = ev.get("recipients") or {}
        group = recipients.get("group") or {}
        members_in_event = {m["id"]: m for m in (group.get("members") or [])}
        for mid in ev.get("behalfOfIds") or []:
            mem = members_in_event.get(mid)
            if not mem:
                continue
            first_name = (mem.get("firstName") or "").strip()
            last_name = (mem.get("lastName") or "").strip()
            canonical = first_name.split()[0].lower() if first_name else mid[:8].lower()
            if canonical not in persons:
                display_name = f"{first_name} {last_name}".strip() or canonical.title()
                persons[canonical] = {"canonical": canonical, "display_name": display_name}
    return sorted(persons.values(), key=lambda m: m["display_name"])


def dedup_members_by_first_token(members: list[dict]) -> list[dict]:
    """Collapse members whose canonical shares the same first underscore-token.

    Used during v1→v2 migration when the old code stored separate entries for
    the same child across groups (e.g. "mathias" and "mathias_g" both collapse
    to "mathias").  The first occurrence's display_name is kept.
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
) -> None:
    """Process one account's raw Spond events into the shared per-member dicts.

    Mutates seen_uids, events_per_member, and tasks_per_member in place.
    Call once per account; seen_uids provides cross-account deduplication.
    """
    for ev in raw_events:
        ev_id = ev.get("id")
        recipients = ev.get("recipients") or {}
        group = recipients.get("group") or {}
        members_in_event = {m.get("id"): m for m in (group.get("members") or [])}
        behalfof_ids = ev.get("behalfOfIds") or []

        tasks_block = ev.get("tasks") or {}
        all_tasks_raw = (tasks_block.get("openTasks") or []) + (
            tasks_block.get("assignedTasks") or []
        )

        # --- Tasks: match assignees to tracked members by first name ---
        for t in all_tasks_raw:
            task_name = t.get("name", "?")
            assignments = t.get("assignments") or {}
            assigned_ids = assignments.get("memberIds") or t.get("memberIds") or []
            required = assignments.get("required") or t.get("required") or 0

            for aid in assigned_ids:
                am = members_in_event.get(aid)
                if not am:
                    continue
                fn = (am.get("firstName") or "").strip()
                canonical = fn.split()[0].lower() if fn else ""
                if canonical not in canonical_names or canonical not in tasks_per_member:
                    continue
                task_uid_key = f"{ev_id}::{task_name}"
                if task_uid_key in tasks_per_member[canonical]:
                    continue
                co_assignees = []
                for other_id in assigned_ids:
                    if other_id == aid:
                        continue
                    om = members_in_event.get(other_id)
                    if om:
                        o_fn_parts = (om.get("firstName") or "").split()
                        o_ln_parts = (om.get("lastName") or "").split()
                        ofn = o_fn_parts[0] if o_fn_parts else ""
                        oln = o_ln_parts[0] if o_ln_parts else ""
                        co_assignees.append(f"{ofn} {oln}".strip() or "?")
                tasks_per_member[canonical][task_uid_key] = {
                    "task_uid_key": task_uid_key,
                    "event_uid": ev_id,
                    "task_name": task_name,
                    "event_title": ev.get("heading", "?"),
                    "start": ev.get("startTimestamp"),
                    "end": ev.get("endTimestamp"),
                    "location": ((ev.get("location") or {}).get("feature") or ""),
                    "address": ((ev.get("location") or {}).get("address") or ""),
                    "required": required,
                    "assigned_count": len(assigned_ids),
                    "co_assignees": co_assignees,
                    "cancelled": bool(ev.get("cancelled")),
                }

        # --- Events: match behalfOfIds to tracked members by first name ---
        responses = ev.get("responses") or {}
        accepted = set(responses.get("acceptedIds") or [])
        declined = set(responses.get("declinedIds") or [])
        waiting = set(responses.get("waitinglistIds") or [])
        unanswered = set(responses.get("unansweredIds") or [])

        for mem_id in behalfof_ids:
            mem = members_in_event.get(mem_id)
            if not mem:
                continue
            fn_full = (mem.get("firstName") or "").strip()
            canonical = fn_full.split()[0].lower() if fn_full else ""
            if canonical not in canonical_names or canonical not in seen_uids:
                continue
            if ev_id in seen_uids[canonical]:
                continue  # already seen from another account or group
            seen_uids[canonical].add(ev_id)

            if ev.get("cancelled"):
                status = "cancelled"
            elif mem_id in accepted:
                status = "accepted"
            elif mem_id in declined:
                status = "declined"
            elif mem_id in waiting:
                status = "waitinglist"
            elif mem_id in unanswered:
                status = "unanswered"
            else:
                status = "unknown"

            ln = (mem.get("lastName") or "").strip()
            ln_token = ln.split()[0] if ln else ""
            self_name = f"{fn_full.split()[0]} {ln_token}".strip() if fn_full else ""

            my_tasks: list[dict] = []
            all_tasks_detail: list[dict] = []
            open_tasks_count = 0

            for t in all_tasks_raw:
                task_name = t.get("name", "?")
                assignments = t.get("assignments") or {}
                assigned_ids = assignments.get("memberIds") or t.get("memberIds") or []
                required = assignments.get("required") or t.get("required") or 0
                adults_only = t.get("adultsOnly", False)

                assignee_names = []
                for aid in assigned_ids:
                    am = members_in_event.get(aid)
                    if am:
                        a_fn_parts = (am.get("firstName") or "").split()
                        a_ln_parts = (am.get("lastName") or "").split()
                        fn = a_fn_parts[0] if a_fn_parts else ""
                        ln_a = a_ln_parts[0] if a_ln_parts else ""
                        assignee_names.append(f"{fn} {ln_a}".strip() or "?")

                if mem_id in assigned_ids:
                    my_tasks.append(
                        {
                            "name": task_name,
                            "co_assignees": [n for n in assignee_names if n != self_name],
                            "required": required,
                            "assigned_count": len(assigned_ids),
                        }
                    )

                is_open = bool(required and len(assigned_ids) < required)
                if is_open:
                    open_tasks_count += 1
                all_tasks_detail.append(
                    {
                        "name": task_name,
                        "assigned": assignee_names,
                        "required": required,
                        "is_open": is_open,
                        "adults_only": adults_only,
                    }
                )

            if canonical not in events_per_member:
                continue
            events_per_member[canonical].append(
                {
                    "uid": ev_id,
                    "title": ev.get("heading", "Spond"),
                    "start": ev.get("startTimestamp"),
                    "end": ev.get("endTimestamp"),
                    "location": ((ev.get("location") or {}).get("feature") or ""),
                    "address": ((ev.get("location") or {}).get("address") or ""),
                    "status": status,
                    "my_tasks": my_tasks,
                    "all_tasks": all_tasks_detail,
                    "open_tasks_count": open_tasks_count,
                }
            )
