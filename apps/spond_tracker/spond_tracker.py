"""
Spond -> HA local_calendar sync via AppDaemon.

For each tracked member, writes an .ics file and reloads the corresponding
local_calendar config_entry. Status (accepted/declined/unanswered/...) is
shown as an emoji in SUMMARY and as text in DESCRIPTION. Tasks go in
DESCRIPTION and a dedicated sensor.

Sensors created per member:
  sensor.spond_<canonical>        - state = number of events today
  sensor.spond_<canonical>_tasks  - state = number of tasks assigned to me

Polling: hourly 06-14, every 30 min 15-22:30, idle 23-06.

Localization
------------
User-facing text (calendar SUMMARY/DESCRIPTION + sensor friendly_name) is
loaded from JSON files in the translations/ directory. Set
`language: en` (default) or `language: nb` in apps.yaml. The legacy code
`no` is accepted as an alias for `nb`. Fallback chain on lookup:
lang -> language-without-region -> en. Log messages are always English.
"""

import contextlib
import hashlib
import json
import re
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path

import appdaemon.plugins.hass.hassapi as hass

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Europe/Oslo")
except ImportError:
    TZ = None

from spond import spond as spond_lib

STATUS_EMOJI = {
    "accepted": "✓",
    "declined": "✗",
    "unanswered": "?",
    "waitinglist": "…",
    "unknown": "·",
    "cancelled": "🚫",
}

TRANSLATIONS_DIR = Path(__file__).parent / "translations"


def _load_translations(strings_dir: Path, lang: str) -> tuple[dict, str]:
    """Load the translations JSON file for `lang`.

    Returns (data, resolved_lang). Falls back through:
      lang -> language-base (strip region) -> en.
    The legacy code "no" is mapped to "nb" (Bokmål) for BCP-47 compliance.
    """
    if lang == "no":
        lang = "nb"
    chain: list[str] = [lang]
    if "-" in lang:
        chain.append(lang.split("-", 1)[0])
    if "en" not in chain:
        chain.append("en")
    for code in chain:
        path = strings_dir / f"{code}.json"
        if path.exists():
            return json.loads(path.read_text()), code
    return {}, "en"


def fmt_dt(iso_str: str) -> str:
    """ISO timestamp -> YYYYMMDDTHHMMSSZ for ICS."""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    dt_utc = dt.astimezone(UTC)
    return dt_utc.strftime("%Y%m%dT%H%M%SZ")


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


def read_past_event_blocks(ics_path: str, now_utc: datetime, current_uids: set[str]) -> list[str]:
    """Return VEVENT blocks from existing ICS for events with DTSTART < now
    that are NOT in current_uids (Spond no longer returns them -> preserve
    them as history).
    """
    try:
        content = Path(ics_path).read_text()
    except FileNotFoundError:
        return []
    past_blocks = []
    blocks = re.findall(r"BEGIN:VEVENT.*?END:VEVENT", content, re.DOTALL)
    for block in blocks:
        dt_match = re.search(r"DTSTART[^:]*:(\d{8})(?:T(\d{6})Z?)?", block)
        uid_match = re.search(r"UID:([^\r\n]+)", block)
        if not dt_match:
            continue
        date_str = dt_match.group(1)
        time_str = dt_match.group(2) or "000000"
        try:
            dt = datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            continue
        if dt >= now_utc:
            continue
        uid = uid_match.group(1).strip() if uid_match else None
        if uid and uid in current_uids:
            continue
        past_blocks.append(block.strip())
    return past_blocks


def ics_escape(s: str | None) -> str:
    if s is None:
        return ""
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


class SpondTracker(hass.Hass):
    async def initialize(self) -> None:
        self.accounts = self.args.get("accounts", [])
        self.members = self.args.get("members", [])
        requested_lang = self.args.get("language", "en")
        if requested_lang == "no":
            self.log(
                "language='no' is deprecated; use 'nb' (Bokmål) instead. Continuing with 'nb'.",
                level="WARNING",
            )
        self.strings, self.lang = _load_translations(TRANSLATIONS_DIR, requested_lang)
        if self.lang != ("nb" if requested_lang == "no" else requested_lang):
            self.log(
                f"Unknown language {requested_lang!r}, fell back to {self.lang!r}",
                level="WARNING",
            )
        # Per-member dict[uid -> fingerprint] from the previous poll, used
        # for change detection between polls.
        self.previous_state = None
        if not self.accounts or not self.members:
            self.log("No accounts/members configured", level="ERROR")
            return
        # Initial fetch in 10 seconds
        self.run_in(self.poll_callback, 10)
        # Hourly 06-14 (9 polls)
        for h in range(6, 15):
            self.run_daily(self.poll_callback, f"{h:02d}:00:00")
        # Every 30 min 15:00 - 22:30 (16 polls)
        for h in range(15, 23):
            self.run_daily(self.poll_callback, f"{h:02d}:00:00")
            self.run_daily(self.poll_callback, f"{h:02d}:30:00")
        # No polling 23-06 (quiet hours)
        self.log(
            f"SpondTracker init: {len(self.accounts)} account(s), "
            f"{len(self.members)} member(s), 25 daily poll times, "
            f"language={self.lang}"
        )

    def t(self, key: str, **fmt: object) -> str:
        """Look up a translation by dotted path (e.g. 'calendar.location_label').

        Returns the dotted key itself if the translation is missing — this
        makes missing strings visible rather than silently empty.
        """
        cur: object = self.strings
        for part in key.split("."):
            if not isinstance(cur, dict):
                return key
            cur = cur.get(part)
            if cur is None:
                return key
        if not isinstance(cur, str):
            return key
        return cur.format(**fmt) if fmt else cur

    async def poll_callback(self, kwargs: dict) -> None:
        now_local = datetime.now(TZ) if TZ else datetime.now()
        self.log(f"Spond: polling at {now_local.strftime('%H:%M')}")
        try:
            await self.fetch_and_update()
        except Exception as e:
            self.log(f"Spond polling error: {e!r}", level="ERROR")
            self.log(traceback.format_exc(), level="ERROR")

    async def fetch_and_update(self) -> None:
        self._pending_state: dict = {}
        events_per_member = {m["canonical"]: [] for m in self.members}
        seen_uids = {m["canonical"]: set() for m in self.members}
        # Per-canonical task list. Tasks may come from events where the
        # tracked member is NOT a direct recipient — e.g. an account
        # assigned bake-sale duty on a group event where it isn't itself
        # invited.
        tasks_per_canonical = {m["canonical"]: [] for m in self.members}
        seen_task_uids = {m["canonical"]: set() for m in self.members}
        canonicals = {m["canonical"].lower() for m in self.members}

        for acc in self.accounts:
            acc_name = acc.get("name", "?")
            try:
                s = spond_lib.Spond(username=acc["username"], password=acc["password"])
                min_end = datetime.now(UTC)
                max_end = min_end + timedelta(days=60)
                raw_events = await s.get_events(min_end=min_end, max_end=max_end, max_events=200)
                self.log(f"Spond[{acc_name}]: fetched {len(raw_events)} events")
                with contextlib.suppress(Exception):
                    await s.clientsession.close()
            except Exception as e:
                self.log(
                    f"Spond[{acc_name}] login/fetch error: {e!r}",
                    level="ERROR",
                )
                continue

            for ev in raw_events:
                ev_id = ev.get("id")
                recipients = ev.get("recipients") or {}
                group = recipients.get("group") or {}
                members_in_event = group.get("members") or []
                id_to_member = {m.get("id"): m for m in members_in_event}

                # behalfOfIds = members this account can respond on behalf of
                behalfof_ids = ev.get("behalfOfIds") or []

                responses = ev.get("responses") or {}
                accepted = set(responses.get("acceptedIds") or [])
                declined = set(responses.get("declinedIds") or [])
                waiting = set(responses.get("waitinglistIds") or [])
                unanswered = set(responses.get("unansweredIds") or [])

                tasks_block = ev.get("tasks") or {}
                # API exposes "openTasks" (unassigned) and "assignedTasks"
                all_tasks = (tasks_block.get("openTasks") or []) + (
                    tasks_block.get("assignedTasks") or []
                )

                # Check whether any tracked member is an assignee on any
                # task. This is independent of behalfOfIds — an account may
                # be assigned tasks on events where it is not itself the
                # recipient.
                for t in all_tasks:
                    task_name = t.get("name", "?")
                    assignments = t.get("assignments") or {}
                    assigned_ids = assignments.get("memberIds") or t.get("memberIds") or []
                    required = assignments.get("required") or t.get("required") or 0
                    for aid in assigned_ids:
                        am = id_to_member.get(aid)
                        if not am:
                            continue
                        fn_full = (am.get("firstName") or "").strip()
                        fw = fn_full.split()[0].lower() if fn_full else ""
                        if fw not in canonicals:
                            continue
                        task_uid_key = f"{ev_id}::{task_name}"
                        if task_uid_key in seen_task_uids[fw]:
                            continue
                        seen_task_uids[fw].add(task_uid_key)
                        co_assignees = []
                        for other_id in assigned_ids:
                            if other_id == aid:
                                continue
                            om = id_to_member.get(other_id)
                            if om:
                                ofn = (om.get("firstName") or "").split()[0]
                                oln = (om.get("lastName") or "").split()[0]
                                co_assignees.append(f"{ofn} {oln}".strip() or "?")
                        tasks_per_canonical[fw].append(
                            {
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
                        )

                for mem_id in behalfof_ids:
                    mem = id_to_member.get(mem_id)
                    if not mem:
                        continue
                    first_name_full = (mem.get("firstName") or "").strip()
                    # Match first word of firstName (e.g. "Ola" from
                    # "Ola Nordmann")
                    first_word = first_name_full.split()[0].lower() if first_name_full else ""
                    if first_word not in canonicals:
                        continue
                    canonical = first_word
                    if ev_id in seen_uids[canonical]:
                        continue
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

                    # Structured task details
                    my_tasks = []  # tasks this member is on
                    all_tasks_detail = []  # all tasks on the event with assignee names
                    open_tasks_count = 0  # number of tasks short on assignees
                    for t in all_tasks:
                        task_name = t.get("name", "?")
                        assignments = t.get("assignments") or {}
                        assigned_ids = assignments.get("memberIds") or t.get("memberIds") or []
                        required = assignments.get("required") or t.get("required") or 0
                        adults_only = t.get("adultsOnly", False)
                        assignee_names = []
                        for aid in assigned_ids:
                            am = id_to_member.get(aid)
                            if am:
                                fn = (am.get("firstName") or "").split()[0]
                                ln = (am.get("lastName") or "").split()[0]
                                assignee_names.append(f"{fn} {ln}".strip() or "?")
                        if mem_id in assigned_ids:
                            self_name = (
                                f"{first_name_full.split()[0]} "
                                f"{(mem.get('lastName') or '').split()[0]}"
                            ).strip()
                            my_tasks.append(
                                {
                                    "name": task_name,
                                    "co_assignees": [n for n in assignee_names if n != self_name],
                                    "required": required,
                                    "assigned_count": len(assigned_ids),
                                }
                            )
                        is_open = required and len(assigned_ids) < required
                        if is_open:
                            open_tasks_count += 1
                        all_tasks_detail.append(
                            {
                                "name": task_name,
                                "assigned": assignee_names,
                                "required": required,
                                "is_open": bool(is_open),
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
                            "from_account": acc_name,
                        }
                    )

        now_local = datetime.now(TZ) if TZ else datetime.now()
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        dtstamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

        for mem_cfg in self.members:
            canonical = mem_cfg["canonical"]
            entry_id = mem_cfg.get("config_entry_id")
            calendar_file = (
                mem_cfg.get("calendar_file")
                or f"/homeassistant/.storage/local_calendar.spond_{canonical}.ics"
            )
            evs = sorted(
                events_per_member[canonical],
                key=lambda e: e.get("start") or "",
            )
            my_task_events = sorted(
                tasks_per_canonical[canonical],
                key=lambda t: t.get("start") or "",
            )

            # Preserve historic events (DTSTART < now) that Spond no longer
            # returns.
            now_utc = datetime.now(UTC)
            current_uids = {stable_uid_for(e["uid"], canonical) for e in evs}
            current_uids |= {
                stable_uid_for(f"task::{t['task_uid_key']}", canonical) for t in my_task_events
            }
            past_blocks = read_past_event_blocks(calendar_file, now_utc, current_uids)

            ics_lines = [
                "BEGIN:VCALENDAR",
                "PRODID:-//homeassistant.io//local_calendar 1.0//EN",
                "VERSION:2.0",
            ]
            for block in past_blocks:
                ics_lines.extend(block.split("\n"))
            for e in evs:
                if e.get("status") == "declined":
                    continue  # declined events are not shown
                if not e.get("start") or not e.get("end"):
                    continue
                try:
                    start_ics = fmt_dt(e["start"])
                    end_ics = fmt_dt(e["end"])
                except Exception:
                    continue
                emoji = STATUS_EMOJI.get(e["status"], "")
                if e["status"] == "cancelled":
                    summary = (f"{emoji} {self.t('calendar.cancelled_prefix')}{e['title']}").strip()
                else:
                    summary = f"{emoji} {e['title']}".strip()
                desc_parts = [f"{self.t('calendar.status_label')}: {e['status']}"]
                if e["location"]:
                    desc_parts.append(f"{self.t('calendar.location_label')}: {e['location']}")
                if e["address"]:
                    desc_parts.append(f"{self.t('calendar.address_label')}: {e['address']}")
                if e["my_tasks"]:
                    lines = [self.t("calendar.my_tasks_header")]
                    for t in e["my_tasks"]:
                        suffix = ""
                        if t.get("required"):
                            suffix = (
                                f" ({t['assigned_count']}/{t['required']} "
                                f"{self.t('calendar.signed_up_suffix')})"
                            )
                        co = t.get("co_assignees") or []
                        co_str = (
                            f" — {self.t('calendar.co_assignees_with')}: {', '.join(co)}"
                            if co
                            else ""
                        )
                        lines.append(f"  • {t['name']}{suffix}{co_str}")
                    desc_parts.append("\n".join(lines))
                if e["all_tasks"]:
                    lines = [self.t("calendar.all_tasks_header")]
                    for t in e["all_tasks"]:
                        assigned = t.get("assigned") or []
                        if t.get("required"):
                            status_str = f"{len(assigned)}/{t['required']}" + (
                                f" — {self.t('calendar.open_slot')}" if t["is_open"] else ""
                            )
                        else:
                            status_str = f"{len(assigned)} {self.t('calendar.signed_up_suffix')}"
                        names = f": {', '.join(assigned)}" if assigned else ""
                        adults = (
                            f" ({self.t('calendar.adults_only')})" if t.get("adults_only") else ""
                        )
                        lines.append(f"  • {t['name']} [{status_str}]{adults}{names}")
                    desc_parts.append("\n".join(lines))
                description = "\n".join(desc_parts)
                stable_uid = hashlib.md5(f"{e['uid']}-{canonical}".encode()).hexdigest()
                uid = f"{stable_uid}@spond-sync.local"
                ics_lines.extend(
                    [
                        "BEGIN:VEVENT",
                        f"DTSTAMP:{dtstamp}",
                        f"UID:{uid}",
                        f"DTSTART:{start_ics}",
                        f"DTEND:{end_ics}",
                        f"SUMMARY:{ics_escape(summary)}",
                        f"DESCRIPTION:{ics_escape(description)}",
                        f"LOCATION:{ics_escape(e['location'])}",
                        f"CREATED:{dtstamp}",
                        "SEQUENCE:0",
                        "END:VEVENT",
                    ]
                )
            # Task-VEVENTs (one calendar event per task)
            for t in my_task_events:
                if not t.get("start") or not t.get("end"):
                    continue
                try:
                    start_ics = fmt_dt(t["start"])
                    end_ics = fmt_dt(t["end"])
                except Exception:
                    continue
                cancelled_prefix = (
                    f"🚫 {self.t('calendar.cancelled_prefix')}" if t.get("cancelled") else ""
                )
                task_summary = f"📋 {cancelled_prefix}{t['task_name']} — {t['event_title']}"
                task_desc_parts = [
                    f"{self.t('calendar.task_for')} "
                    f"{mem_cfg.get('display_name', canonical.title())}",
                    f"{self.t('calendar.on_event')}: {t['event_title']}",
                ]
                if t.get("required"):
                    task_desc_parts.append(
                        f"{self.t('calendar.task_signed_up')}: "
                        f"{t['assigned_count']}/{t['required']}"
                    )
                if t.get("co_assignees"):
                    task_desc_parts.append(
                        f"{self.t('calendar.task_with')}: " + ", ".join(t["co_assignees"])
                    )
                if t.get("location"):
                    task_desc_parts.append(f"{self.t('calendar.location_label')}: {t['location']}")
                if t.get("address"):
                    task_desc_parts.append(f"{self.t('calendar.address_label')}: {t['address']}")
                if t.get("cancelled"):
                    task_desc_parts.append(self.t("calendar.main_event_cancelled"))
                task_description = "\n".join(task_desc_parts)
                task_uid = stable_uid_for(f"task::{t['task_uid_key']}", canonical)
                ics_lines.extend(
                    [
                        "BEGIN:VEVENT",
                        f"DTSTAMP:{dtstamp}",
                        f"UID:{task_uid}",
                        f"DTSTART:{start_ics}",
                        f"DTEND:{end_ics}",
                        f"SUMMARY:{ics_escape(task_summary)}",
                        f"DESCRIPTION:{ics_escape(task_description)}",
                        f"LOCATION:{ics_escape(t.get('location') or '')}",
                        f"CREATED:{dtstamp}",
                        "SEQUENCE:0",
                        "END:VEVENT",
                    ]
                )

            ics_lines.append("END:VCALENDAR")
            ics_content = "\n".join(ics_lines) + "\n"

            try:
                Path(calendar_file).write_text(ics_content)
                self.log(f"Spond[{canonical}]: wrote {len(evs)} events to {calendar_file}")
            except Exception as e:
                self.log(
                    f"Spond[{canonical}]: failed to write {calendar_file}: {e!r}",
                    level="ERROR",
                )
                continue

            if entry_id:
                try:
                    await self.call_service(
                        "homeassistant/reload_config_entry",
                        entry_id=entry_id,
                    )
                    self.log(f"Spond[{canonical}]: reloaded config_entry {entry_id}")
                except Exception as e:
                    self.log(
                        f"Spond[{canonical}]: reload failed: {e!r}",
                        level="ERROR",
                    )

            today = []
            for e in evs:
                if e.get("status") in ("cancelled", "declined"):
                    continue  # do not count cancelled or declined events
                try:
                    dt = datetime.fromisoformat((e.get("start") or "").replace("Z", "+00:00"))
                    if TZ:
                        dt = dt.astimezone(TZ)
                    if today_start <= dt < today_end:
                        today.append(e)
                except Exception:
                    pass

            display = mem_cfg.get("display_name", canonical.title())

            # Filter declined/cancelled out of what we show in UI
            visible_evs = [e for e in evs if e.get("status") not in ("declined", "cancelled")]
            next_event = visible_evs[0] if visible_evs else None

            self.set_state(
                f"sensor.spond_{canonical}",
                state=str(len(today)),
                attributes={
                    "friendly_name": self.t("sensors.events_friendly", name=display),
                    "icon": "mdi:calendar-account",
                    "today_count": len(today),
                    "today_events": today,
                    "next_event": next_event,
                    "upcoming_count": len(visible_evs),
                    "upcoming_events": visible_evs[:10],
                    "last_updated": now_local.isoformat(),
                },
            )

            tasks_list = []
            for t in my_task_events:
                if t.get("cancelled"):
                    continue
                tasks_list.append(
                    {
                        "task": t["task_name"],
                        "event": t["event_title"],
                        "start": t["start"],
                        "end": t["end"],
                        "location": t["location"],
                        "co_assignees": t.get("co_assignees", []),
                        "required": t.get("required", 0),
                        "assigned_count": t.get("assigned_count", 0),
                    }
                )
            self.set_state(
                f"sensor.spond_{canonical}_tasks",
                state=str(len(tasks_list)),
                attributes={
                    "friendly_name": self.t("sensors.tasks_friendly", name=display),
                    "icon": "mdi:clipboard-list-outline",
                    "tasks": tasks_list,
                    "last_updated": now_local.isoformat(),
                },
            )
            self.log(
                f"Spond[{canonical}]: {len(today)} today, "
                f"{len(evs)} upcoming, {len(tasks_list)} tasks"
            )

            # --- Change detection ---
            current_fp = {e["uid"]: event_fingerprint(e) for e in evs}
            current_full = {e["uid"]: e for e in evs}
            if self.previous_state is not None:
                prev = self.previous_state.get(canonical, {})
                # Added
                for uid in set(current_fp) - set(prev):
                    e = current_full[uid]
                    self.log(f"Spond[{canonical}] ADDED: {e.get('title')}")
                    self.fire_event(
                        "spond_event_added",
                        member=canonical,
                        title=e.get("title"),
                        start=e.get("start"),
                        location=e.get("location"),
                        status=e.get("status"),
                        uid=uid,
                    )
                # Removed
                for uid in set(prev) - set(current_fp):
                    self.log(f"Spond[{canonical}] REMOVED: uid={uid}")
                    self.fire_event(
                        "spond_event_removed",
                        member=canonical,
                        title=prev[uid].get("title"),
                        start=prev[uid].get("start"),
                        uid=uid,
                    )
                # Changed
                for uid in set(current_fp) & set(prev):
                    if current_fp[uid] != prev[uid]:
                        e = current_full[uid]
                        changed_fields = [
                            k for k in current_fp[uid] if current_fp[uid].get(k) != prev[uid].get(k)
                        ]
                        self.log(
                            f"Spond[{canonical}] CHANGED: {e.get('title')} fields={changed_fields}"
                        )
                        self.fire_event(
                            "spond_event_changed",
                            member=canonical,
                            title=e.get("title"),
                            start=e.get("start"),
                            status=e.get("status"),
                            changed_fields=changed_fields,
                            uid=uid,
                        )
                        # Special-case: cancellation
                        if (
                            current_fp[uid].get("status") == "cancelled"
                            and prev[uid].get("status") != "cancelled"
                        ):
                            self.log(f"Spond[{canonical}] CANCELLED: {e.get('title')}")
                            self.fire_event(
                                "spond_event_cancelled",
                                member=canonical,
                                title=e.get("title"),
                                start=e.get("start"),
                                location=e.get("location"),
                                uid=uid,
                            )
                        # Special-case: new task assigned to me
                        prev_tasks = set(prev[uid].get("my_tasks") or ())
                        cur_tasks = set(current_fp[uid].get("my_tasks") or ())
                        new_tasks = cur_tasks - prev_tasks
                        for t in new_tasks:
                            self.fire_event(
                                "spond_task_assigned",
                                member=canonical,
                                title=e.get("title"),
                                start=e.get("start"),
                                task=t,
                                uid=uid,
                            )

            # Save state for the next poll
            self._pending_state[canonical] = current_fp

        # After all members: commit pending as previous (for next poll)
        self.previous_state = self._pending_state
