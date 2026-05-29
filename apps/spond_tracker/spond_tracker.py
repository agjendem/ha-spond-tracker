"""
Spond -> HA local_calendar sync via AppDaemon.

Per familiemedlem skriver vi en .ics-fil og reloader tilhorende
local_calendar config_entry. Status (akseptert/avslott/ubesvart) vises
som emoji i SUMMARY og som tekst i DESCRIPTION. Oppgaver legges i
DESCRIPTION + en dedikert sensor.

Sensorer som opprettes per medlem:
  sensor.spond_<canonical>          - state = antall events i dag
  sensor.spond_<canonical>_oppgaver - state = antall oppgaver tildelt meg

Polling: 06-15 hver hele time, 15-23 hver halvtime, 23-06 ingen polling.
"""
import hashlib
import re
import traceback
from datetime import datetime, timedelta, timezone
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


def fmt_dt(iso_str):
    """ISO timestamp -> YYYYMMDDTHHMMSSZ for ICS."""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.strftime("%Y%m%dT%H%M%SZ")


def event_fingerprint(e):
    """Subset av event-felter for endrings-deteksjon."""
    my_task_names = tuple(sorted(
        t.get("name") if isinstance(t, dict) else t
        for t in (e.get("my_tasks") or [])
    ))
    all_task_names = tuple(sorted(
        f"{t.get('name')}:{len(t.get('assigned') or [])}/{t.get('required', 0)}"
        if isinstance(t, dict) else t
        for t in (e.get("all_tasks") or [])
    ))
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


def stable_uid_for(spond_uid, canonical):
    h = hashlib.md5(f"{spond_uid}-{canonical}".encode()).hexdigest()
    return f"{h}@spond-sync.local"


def read_past_event_blocks(ics_path, now_utc, current_uids):
    """Returner VEVENT-blokker fra eksisterende ICS for events med DTSTART < now,
    som IKKE er i current_uids (Spond kjenner ikke til dem lenger -> bevar historisk)."""
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
            dt = datetime.strptime(
                f"{date_str}{time_str}", "%Y%m%d%H%M%S"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt >= now_utc:
            continue  # ikke historisk
        uid = uid_match.group(1).strip() if uid_match else None
        if uid and uid in current_uids:
            continue  # Spond har fortsatt eventet -> blir lagt til på nytt
        past_blocks.append(block.strip())
    return past_blocks


def ics_escape(s):
    if s is None:
        return ""
    return (
        s.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


class SpondTracker(hass.Hass):

    async def initialize(self):
        self.accounts = self.args.get("accounts", [])
        self.members = self.args.get("members", [])
        # Per-medlem dict[uid -> fingerprint] fra forrige polling — for endrings-deteksjon
        self.previous_state = None
        if not self.accounts or not self.members:
            self.log("Ingen accounts/members konfigurert", level="ERROR")
            return
        # Initial fetch om 10 sek
        self.run_in(self.poll_callback, 10)
        # Schedule: hver hele time 06-14 (9 polls)
        for h in range(6, 15):
            self.run_daily(self.poll_callback, f"{h:02d}:00:00")
        # Schedule: hver halvtime 15:00 - 22:30 (16 polls)
        for h in range(15, 23):
            self.run_daily(self.poll_callback, f"{h:02d}:00:00")
            self.run_daily(self.poll_callback, f"{h:02d}:30:00")
        # Ingen polling 23-06 (rolig tid)
        self.log(
            f"SpondTracker init: {len(self.accounts)} konto(er), "
            f"{len(self.members)} medlem(mer), 25 daglige poll-tider"
        )

    async def poll_callback(self, kwargs):
        now_local = datetime.now(TZ) if TZ else datetime.now()
        self.log(f"Spond: polling kl {now_local.strftime('%H:%M')}")
        try:
            await self.fetch_and_update()
        except Exception as e:
            self.log(f"Spond polling-feil: {e!r}", level="ERROR")
            self.log(traceback.format_exc(), level="ERROR")

    async def fetch_and_update(self):
        self._pending_state = {}
        events_per_member = {m["canonical"]: [] for m in self.members}
        seen_uids = {m["canonical"]: set() for m in self.members}
        # Separate task-events per canonical (kan komme fra events der du IKKE er recipient,
        # f.eks. forelder med iskjøring-task på barnets trening)
        tasks_per_canonical = {m["canonical"]: [] for m in self.members}
        seen_task_uids = {m["canonical"]: set() for m in self.members}
        canonicals = {m["canonical"].lower() for m in self.members}

        for acc in self.accounts:
            acc_name = acc.get("name", "?")
            try:
                s = spond_lib.Spond(
                    username=acc["username"], password=acc["password"]
                )
                min_end = datetime.now(timezone.utc)
                max_end = min_end + timedelta(days=60)
                raw_events = await s.get_events(
                    min_end=min_end, max_end=max_end, max_events=200
                )
                self.log(f"Spond[{acc_name}]: hentet {len(raw_events)} events")
                try:
                    await s.clientsession.close()
                except Exception:
                    pass
            except Exception as e:
                self.log(
                    f"Spond[{acc_name}] login/fetch-feil: {e!r}", level="ERROR"
                )
                continue

            for ev in raw_events:
                ev_id = ev.get("id")
                recipients = ev.get("recipients") or {}
                group = recipients.get("group") or {}
                members_in_event = group.get("members") or []
                id_to_member = {m.get("id"): m for m in members_in_event}

                # behalfOfIds = medlemmer som denne kontoen kan svare på vegne av
                behalfof_ids = ev.get("behalfOfIds") or []

                responses = ev.get("responses") or {}
                accepted = set(responses.get("acceptedIds") or [])
                declined = set(responses.get("declinedIds") or [])
                waiting = set(responses.get("waitinglistIds") or [])
                unanswered = set(responses.get("unansweredIds") or [])

                tasks_block = ev.get("tasks") or {}
                # API har "openTasks" (ledige) og "assignedTasks" (tildelt)
                all_tasks = (tasks_block.get("openTasks") or []) + (tasks_block.get("assignedTasks") or [])

                # Sjekk om en av VÅRE familiemedlemmer er assignee på noen task
                # (uavhengig av behalfOfIds — kan være forelder med task på barnets event)
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
                        tasks_per_canonical[fw].append({
                            "task_uid_key": task_uid_key,
                            "event_uid": ev_id,
                            "task_name": task_name,
                            "event_title": ev.get("heading", "?"),
                            "start": ev.get("startTimestamp"),
                            "end": ev.get("endTimestamp"),
                            "location": (ev.get("location") or {}).get("feature") or "",
                            "address": (ev.get("location") or {}).get("address") or "",
                            "required": required,
                            "assigned_count": len(assigned_ids),
                            "co_assignees": co_assignees,
                            "cancelled": bool(ev.get("cancelled")),
                        })

                for mem_id in behalfof_ids:
                    mem = id_to_member.get(mem_id)
                    if not mem:
                        continue
                    first_name_full = (mem.get("firstName") or "").strip()
                    # Match på første ord i firstName (f.eks. "Ola" fra "Ola Nordmann")
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

                    # Strukturerte task-detaljer
                    my_tasks = []      # tasks jeg/familiemedlemmet er på
                    all_tasks_detail = []  # alle tasks på eventet med navn på påmeldte
                    open_tasks_count = 0  # antall tasks som mangler folk
                    for t in all_tasks:
                        task_name = t.get("name", "?")
                        assignments = t.get("assignments") or {}
                        assigned_ids = (
                            assignments.get("memberIds")
                            or t.get("memberIds")
                            or []
                        )
                        required = (
                            assignments.get("required") or t.get("required") or 0
                        )
                        adults_only = t.get("adultsOnly", False)
                        # Slå opp navn på påmeldte
                        assignee_names = []
                        for aid in assigned_ids:
                            am = id_to_member.get(aid)
                            if am:
                                fn = (am.get("firstName") or "").split()[0]
                                ln = (am.get("lastName") or "").split()[0]
                                assignee_names.append(f"{fn} {ln}".strip() or "?")
                        if mem_id in assigned_ids:
                            my_tasks.append({
                                "name": task_name,
                                "co_assignees": [n for n in assignee_names if n != f"{first_name_full.split()[0]} {(mem.get('lastName') or '').split()[0]}".strip()],
                                "required": required,
                                "assigned_count": len(assigned_ids),
                            })
                        is_open = required and len(assigned_ids) < required
                        if is_open:
                            open_tasks_count += 1
                        all_tasks_detail.append({
                            "name": task_name,
                            "assigned": assignee_names,
                            "required": required,
                            "is_open": bool(is_open),
                            "adults_only": adults_only,
                        })

                    events_per_member[canonical].append(
                        {
                            "uid": ev_id,
                            "title": ev.get("heading", "Spond"),
                            "start": ev.get("startTimestamp"),
                            "end": ev.get("endTimestamp"),
                            "location": (ev.get("location") or {}).get("feature")
                            or "",
                            "address": (ev.get("location") or {}).get("address")
                            or "",
                            "status": status,
                            "my_tasks": my_tasks,         # list of dicts
                            "all_tasks": all_tasks_detail,  # list of dicts
                            "open_tasks_count": open_tasks_count,
                            "from_account": acc_name,
                        }
                    )

        now_local = datetime.now(TZ) if TZ else datetime.now()
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        for mem_cfg in self.members:
            canonical = mem_cfg["canonical"]
            entry_id = mem_cfg.get("config_entry_id")
            calendar_file = mem_cfg.get(
                "calendar_file"
            ) or f"/homeassistant/.storage/local_calendar.spond_{canonical}.ics"
            evs = sorted(
                events_per_member[canonical], key=lambda e: e.get("start") or ""
            )
            my_task_events = sorted(
                tasks_per_canonical[canonical], key=lambda t: t.get("start") or ""
            )

            # Bevar historiske events (DTSTART < now) som Spond ikke lenger returnerer
            now_utc = datetime.now(timezone.utc)
            current_uids = {stable_uid_for(e["uid"], canonical) for e in evs}
            current_uids |= {
                stable_uid_for(f"task::{t['task_uid_key']}", canonical)
                for t in my_task_events
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
                    continue  # avslåtte events vises ikke
                if not e.get("start") or not e.get("end"):
                    continue
                try:
                    start_ics = fmt_dt(e["start"])
                    end_ics = fmt_dt(e["end"])
                except Exception:
                    continue
                emoji = STATUS_EMOJI.get(e["status"], "")
                if e["status"] == "cancelled":
                    summary = f"{emoji} AVLYST: {e['title']}".strip()
                else:
                    summary = f"{emoji} {e['title']}".strip()
                desc_parts = [f"Status: {e['status']}"]
                if e["location"]:
                    desc_parts.append(f"Sted: {e['location']}")
                if e["address"]:
                    desc_parts.append(f"Adresse: {e['address']}")
                if e["my_tasks"]:
                    lines = ["Mine oppgaver:"]
                    for t in e["my_tasks"]:
                        suffix = ""
                        if t.get("required"):
                            suffix = f" ({t['assigned_count']}/{t['required']} påmeldt)"
                        co = t.get("co_assignees") or []
                        co_str = f" — sammen med: {', '.join(co)}" if co else ""
                        lines.append(f"  • {t['name']}{suffix}{co_str}")
                    desc_parts.append("\n".join(lines))
                if e["all_tasks"]:
                    lines = ["Alle oppgaver:"]
                    for t in e["all_tasks"]:
                        assigned = t.get("assigned") or []
                        if t.get("required"):
                            status_str = (
                                f"{len(assigned)}/{t['required']}"
                                + (" — LEDIG" if t["is_open"] else "")
                            )
                        else:
                            status_str = f"{len(assigned)} påmeldt"
                        names = (
                            f": {', '.join(assigned)}"
                            if assigned else ""
                        )
                        adults = " (kun voksne)" if t.get("adults_only") else ""
                        lines.append(f"  • {t['name']} [{status_str}]{adults}{names}")
                    desc_parts.append("\n".join(lines))
                description = "\n".join(desc_parts)
                stable_uid = hashlib.md5(
                    f"{e['uid']}-{canonical}".encode()
                ).hexdigest()
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
            # Task-VEVENTs (egne kalender-events per oppgave)
            for t in my_task_events:
                if not t.get("start") or not t.get("end"):
                    continue
                try:
                    start_ics = fmt_dt(t["start"])
                    end_ics = fmt_dt(t["end"])
                except Exception:
                    continue
                avlyst_prefix = "🚫 AVLYST: " if t.get("cancelled") else ""
                task_summary = f"📋 {avlyst_prefix}{t['task_name']} — {t['event_title']}"
                task_desc_parts = [
                    f"Oppgave for {mem_cfg.get('display_name', canonical.title())}",
                    f"På event: {t['event_title']}",
                ]
                if t.get("required"):
                    task_desc_parts.append(
                        f"Påmeldt: {t['assigned_count']}/{t['required']}"
                    )
                if t.get("co_assignees"):
                    task_desc_parts.append(
                        "Sammen med: " + ", ".join(t["co_assignees"])
                    )
                if t.get("location"):
                    task_desc_parts.append(f"Sted: {t['location']}")
                if t.get("address"):
                    task_desc_parts.append(f"Adresse: {t['address']}")
                if t.get("cancelled"):
                    task_desc_parts.append("⚠️ Hovedeventet er AVLYST")
                task_description = "\n".join(task_desc_parts)
                task_uid = stable_uid_for(f"task::{t['task_uid_key']}", canonical)
                ics_lines.extend([
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
                ])

            ics_lines.append("END:VCALENDAR")
            ics_content = "\n".join(ics_lines) + "\n"

            try:
                Path(calendar_file).write_text(ics_content)
                self.log(
                    f"Spond[{canonical}]: skrev {len(evs)} events til {calendar_file}"
                )
            except Exception as e:
                self.log(
                    f"Spond[{canonical}]: kunne ikke skrive {calendar_file}: {e!r}",
                    level="ERROR",
                )
                continue

            if entry_id:
                try:
                    await self.call_service(
                        "homeassistant/reload_config_entry", entry_id=entry_id
                    )
                    self.log(
                        f"Spond[{canonical}]: reloaded config_entry {entry_id}"
                    )
                except Exception as e:
                    self.log(
                        f"Spond[{canonical}]: reload feilet: {e!r}", level="ERROR"
                    )

            today = []
            for e in evs:
                if e.get("status") in ("cancelled", "declined"):
                    continue  # tell ikke avlyste eller avslåtte
                try:
                    dt = datetime.fromisoformat(
                        (e.get("start") or "").replace("Z", "+00:00")
                    )
                    if TZ:
                        dt = dt.astimezone(TZ)
                    if today_start <= dt < today_end:
                        today.append(e)
                except Exception:
                    pass

            display = mem_cfg.get("display_name", canonical.title())

            # Filtrer ut declined/cancelled fra det vi viser i UI
            visible_evs = [
                e for e in evs
                if e.get("status") not in ("declined", "cancelled")
            ]
            next_event = visible_evs[0] if visible_evs else None

            self.set_state(
                f"sensor.spond_{canonical}",
                state=str(len(today)),
                attributes={
                    "friendly_name": f"Spond {display}",
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
                tasks_list.append({
                    "task": t["task_name"],
                    "event": t["event_title"],
                    "start": t["start"],
                    "end": t["end"],
                    "location": t["location"],
                    "co_assignees": t.get("co_assignees", []),
                    "required": t.get("required", 0),
                    "assigned_count": t.get("assigned_count", 0),
                })
            self.set_state(
                f"sensor.spond_{canonical}_oppgaver",
                state=str(len(tasks_list)),
                attributes={
                    "friendly_name": f"Spond oppgaver {display}",
                    "icon": "mdi:clipboard-list-outline",
                    "tasks": tasks_list,
                    "last_updated": now_local.isoformat(),
                },
            )
            self.log(
                f"Spond[{canonical}]: {len(today)} idag, "
                f"{len(evs)} kommende, {len(tasks_list)} oppgaver"
            )

            # --- Endrings-deteksjon ---
            current_fp = {e["uid"]: event_fingerprint(e) for e in evs}
            current_full = {e["uid"]: e for e in evs}
            if self.previous_state is not None:
                prev = self.previous_state.get(canonical, {})
                # Lagt til
                for uid in set(current_fp) - set(prev):
                    e = current_full[uid]
                    self.log(f"Spond[{canonical}] LAGT TIL: {e.get('title')}")
                    self.fire_event(
                        "spond_event_added",
                        member=canonical,
                        title=e.get("title"),
                        start=e.get("start"),
                        location=e.get("location"),
                        status=e.get("status"),
                        uid=uid,
                    )
                # Fjernet
                for uid in set(prev) - set(current_fp):
                    self.log(f"Spond[{canonical}] FJERNET: uid={uid}")
                    self.fire_event(
                        "spond_event_removed",
                        member=canonical,
                        title=prev[uid].get("title"),
                        start=prev[uid].get("start"),
                        uid=uid,
                    )
                # Endret
                for uid in set(current_fp) & set(prev):
                    if current_fp[uid] != prev[uid]:
                        e = current_full[uid]
                        changed_fields = [
                            k for k in current_fp[uid]
                            if current_fp[uid].get(k) != prev[uid].get(k)
                        ]
                        self.log(
                            f"Spond[{canonical}] ENDRET: {e.get('title')} fields={changed_fields}"
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
                        # Spesial: avlysning
                        if (
                            current_fp[uid].get("status") == "cancelled"
                            and prev[uid].get("status") != "cancelled"
                        ):
                            self.log(
                                f"Spond[{canonical}] AVLYST: {e.get('title')}"
                            )
                            self.fire_event(
                                "spond_event_cancelled",
                                member=canonical,
                                title=e.get("title"),
                                start=e.get("start"),
                                location=e.get("location"),
                                uid=uid,
                            )
                        # Spesial: ny oppgave tildelt meg
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

            # Lagre tilstand for neste polling
            self._pending_state[canonical] = current_fp

        # Etter alle medlemmer: commit pending som previous (for neste poll)
        self.previous_state = self._pending_state
