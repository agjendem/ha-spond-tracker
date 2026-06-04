"""DataUpdateCoordinator for Spond Tracker."""

import contextlib
import logging
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from spond import spond as spond_lib

from .const import (
    CONF_ACCOUNTS,
    CONF_MEMBERS,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_USERNAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .spond_helpers import event_fingerprint

_LOGGER = logging.getLogger(__name__)


@dataclass
class CoordinatorData:
    """Data returned by a single Spond poll."""

    events: dict[str, list[dict]] = field(default_factory=dict)
    # canonical -> list of event dicts, sorted by start, all statuses included
    tasks: dict[str, list[dict]] = field(default_factory=dict)
    # canonical -> list of task dicts, sorted by start
    polled_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SpondDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Coordinator that polls one or more Spond accounts on a fixed interval."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        poll_minutes = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=poll_minutes),
        )
        self.entry = entry
        self._previous_fingerprints: dict[str, dict[str, dict]] = {}

    @property
    def language(self) -> str:
        return self.hass.config.language

    def _get_accounts(self) -> list[dict]:
        """Return all configured accounts, supporting both v1 and v2 data schemas."""
        if CONF_ACCOUNTS in self.entry.data:
            return self.entry.data[CONF_ACCOUNTS]
        # Legacy v1 schema fallback
        return [
            {
                CONF_USERNAME: self.entry.data[CONF_USERNAME],
                CONF_PASSWORD: self.entry.data[CONF_PASSWORD],
            }
        ]

    async def _async_update_data(self) -> CoordinatorData:
        tracked_members: list[dict] = self.entry.data.get(CONF_MEMBERS, [])
        canonical_names = {m["canonical"] for m in tracked_members}

        events_per_member: dict[str, list[dict]] = {m["canonical"]: [] for m in tracked_members}
        tasks_per_member: dict[str, dict[str, dict]] = {m["canonical"]: {} for m in tracked_members}
        # seen_uids deduplicates events that appear in multiple accounts for the same member
        seen_uids: dict[str, set[str]] = {m["canonical"]: set() for m in tracked_members}

        accounts = self._get_accounts()
        any_success = False

        for acc in accounts:
            acc_username = acc[CONF_USERNAME]
            s = spond_lib.Spond(username=acc_username, password=acc[CONF_PASSWORD])
            try:
                now_utc = datetime.now(UTC)
                raw_events = await s.get_events(
                    min_end=now_utc,
                    max_end=now_utc + timedelta(days=60),
                    max_events=200,
                )
                _LOGGER.debug("Spond[%s]: fetched %d events", acc_username, len(raw_events))
                any_success = True
            except Exception as e:
                _LOGGER.error(
                    "Spond[%s] fetch error: %r\n%s", acc_username, e, traceback.format_exc()
                )
                continue  # try remaining accounts
            finally:
                with contextlib.suppress(Exception):
                    await s.clientsession.close()

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
                        if canonical not in canonical_names:
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
                                ofn = (om.get("firstName") or "").split()[0]
                                oln = (om.get("lastName") or "").split()[0]
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
                    if canonical not in canonical_names:
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
                    self_name = f"{fn_full.split()[0]} {ln.split()[0]}".strip() if fn_full else ""

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
                                fn = (am.get("firstName") or "").split()[0]
                                ln_a = (am.get("lastName") or "").split()[0]
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

        if not any_success and accounts:
            raise UpdateFailed("All Spond accounts failed to fetch events")

        # Sort by start time
        for canonical in events_per_member:
            events_per_member[canonical].sort(key=lambda e: e.get("start") or "")

        tasks_data: dict[str, list[dict]] = {
            canonical: sorted(task_dict.values(), key=lambda t: t.get("start") or "")
            for canonical, task_dict in tasks_per_member.items()
        }

        # Change detection: fire HA bus events for diffs since last poll
        for mem_cfg in tracked_members:
            canonical = mem_cfg["canonical"]
            evs = events_per_member[canonical]
            current_fp = {e["uid"]: event_fingerprint(e) for e in evs}
            current_full = {e["uid"]: e for e in evs}
            prev = self._previous_fingerprints.get(canonical, {})

            if prev:
                for uid in set(current_fp) - set(prev):
                    e = current_full[uid]
                    self.hass.bus.async_fire(
                        "spond_event_added",
                        {
                            "member": canonical,
                            "title": e.get("title"),
                            "start": e.get("start"),
                            "location": e.get("location"),
                            "status": e.get("status"),
                            "uid": uid,
                        },
                    )
                for uid in set(prev) - set(current_fp):
                    self.hass.bus.async_fire(
                        "spond_event_removed",
                        {
                            "member": canonical,
                            "title": prev[uid].get("title"),
                            "start": prev[uid].get("start"),
                            "uid": uid,
                        },
                    )
                for uid in set(current_fp) & set(prev):
                    if current_fp[uid] != prev[uid]:
                        e = current_full[uid]
                        changed_fields = [
                            k for k in current_fp[uid] if current_fp[uid].get(k) != prev[uid].get(k)
                        ]
                        self.hass.bus.async_fire(
                            "spond_event_changed",
                            {
                                "member": canonical,
                                "title": e.get("title"),
                                "start": e.get("start"),
                                "status": e.get("status"),
                                "changed_fields": changed_fields,
                                "uid": uid,
                            },
                        )
                        if (
                            current_fp[uid].get("status") == "cancelled"
                            and prev[uid].get("status") != "cancelled"
                        ):
                            self.hass.bus.async_fire(
                                "spond_event_cancelled",
                                {
                                    "member": canonical,
                                    "title": e.get("title"),
                                    "start": e.get("start"),
                                    "location": e.get("location"),
                                    "uid": uid,
                                },
                            )
                        prev_tasks = set(prev[uid].get("my_tasks") or ())
                        cur_tasks = set(current_fp[uid].get("my_tasks") or ())
                        for task in cur_tasks - prev_tasks:
                            self.hass.bus.async_fire(
                                "spond_task_assigned",
                                {
                                    "member": canonical,
                                    "title": e.get("title"),
                                    "start": e.get("start"),
                                    "task": task,
                                    "uid": uid,
                                },
                            )

            self._previous_fingerprints[canonical] = current_fp

        _LOGGER.debug(
            "Spond poll complete: %s",
            {c: len(evs) for c, evs in events_per_member.items()},
        )
        return CoordinatorData(
            events=events_per_member,
            tasks=tasks_data,
            polled_at=datetime.now(UTC),
        )
