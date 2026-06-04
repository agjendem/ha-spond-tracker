"""Pure-function helpers for Spond Tracker.

Nothing here touches HA, AppDaemon, or Spond directly — all functions
are side-effect-free except `read_past_event_blocks` which only reads disk.
"""

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path


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


def ics_escape(s: str | None) -> str:
    if s is None:
        return ""
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def read_past_event_blocks(ics_path: str, now_utc: datetime, current_uids: set[str]) -> list[str]:
    """Return VEVENT blocks from an existing ICS for past events not in current_uids."""
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
