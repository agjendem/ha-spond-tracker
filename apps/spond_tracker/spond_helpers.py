"""Pure-function helpers for spond_tracker.

Kept separate from spond_tracker.py so the main class file stays focused
on orchestration and lifecycle. Nothing here touches AppDaemon, HA, or
Spond directly — everything is side-effect-free except `read_past_event_blocks`,
which only reads from disk.
"""

import hashlib
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from croniter import croniter


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
    """Return VEVENT blocks from an existing ICS for events with DTSTART < now
    that are NOT in current_uids (Spond no longer returns them — preserve as
    history so the user keeps their record).
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


def cron_to_daily_times(cron_expr: str) -> set[tuple[int, int]]:
    """Expand a 5-field cron expression to {(hour, minute), ...} pairs.

    Only intraday schedules are supported: the day-of-month, month, and
    day-of-week fields must all be `*`. This keeps the scheduling model
    simple — AppDaemon's run_daily fires at the same time every day,
    and applying date-based filtering would need a different mechanism
    that callers should add explicitly.

    Raises ValueError on:
      - Wrong number of fields.
      - Any of dom/mon/dow being something other than `*`.
      - An expression croniter can't parse.
    """
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(
            f"cron must have 5 fields (m h dom mon dow), got {len(parts)}: {cron_expr!r}"
        )
    _minute, _hour, dom, mon, dow = parts
    if dom != "*" or mon != "*" or dow != "*":
        raise ValueError(
            f"day-of-month, month, and day-of-week must be '*' "
            f"(got dom={dom!r} mon={mon!r} dow={dow!r}); only intraday schedules are supported"
        )
    base = datetime(2026, 1, 1, 0, 0, 0)
    try:
        itr = croniter(cron_expr, base - timedelta(seconds=1))
    except Exception as e:
        raise ValueError(f"invalid cron expression {cron_expr!r}: {e}") from e
    end = base + timedelta(days=1)
    times: set[tuple[int, int]] = set()
    while True:
        fire = itr.get_next(datetime)
        if fire >= end:
            break
        times.add((fire.hour, fire.minute))
    return times
