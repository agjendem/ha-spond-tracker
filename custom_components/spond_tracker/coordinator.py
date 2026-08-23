"""DataUpdateCoordinator for Spond Tracker."""

import contextlib
import logging
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from spond import spond as spond_lib

from .const import (
    CONF_ACCOUNTS,
    CONF_EVENT_WINDOW_DAYS,
    CONF_INCLUDE_UNINVITED,
    CONF_MEMBERS,
    CONF_NIGHT_END,
    CONF_NIGHT_POLL_INTERVAL,
    CONF_NIGHT_START,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_UNINVITED_HORIZON_DAYS,
    CONF_USERNAME,
    DEFAULT_EVENT_WINDOW_DAYS,
    DEFAULT_INCLUDE_UNINVITED,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_POLL_INTERVAL,
    DEFAULT_NIGHT_START,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_UNINVITED_HORIZON_DAYS,
    DOMAIN,
    SNOOZE_STORAGE_KEY,
    SNOOZE_STORAGE_VERSION,
)
from .spond_helpers import (
    event_fingerprint,
    next_poll_minutes,
    parse_clock,
    process_raw_events,
)
from .spond_i18n import TRANSLATIONS_DIR, load_translations

_LOGGER = logging.getLogger(__name__)

# Spond returns roughly 20 events per account over 60 days with uninvited ones
# filtered out, and roughly 170 with them included. The ceiling sits well clear
# of both, because hitting it drops the far end of the window without a word.
# It is a safety net rather than a preference, so it stays a constant while the
# windows themselves are configurable.
MAX_EVENTS = 400


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
        self.strings: dict = {}
        self._strings_lang: str = ""
        self._consecutive_failures: int = 0
        self._snooze_store: Store = Store(hass, SNOOZE_STORAGE_VERSION, SNOOZE_STORAGE_KEY)
        # task_uid_key -> ISO timestamp until which the task is hushed
        self.snoozed: dict[str, str] = {}

    @property
    def language(self) -> str:
        return self.hass.config.language

    async def _load_strings(self) -> None:
        lang = self.language
        if lang != self._strings_lang:
            strings, resolved = await self.hass.async_add_executor_job(
                load_translations, TRANSLATIONS_DIR, lang
            )
            self.strings = strings
            self._strings_lang = resolved

    def _get_accounts(self) -> list[dict]:
        return self.entry.data.get(CONF_ACCOUNTS, [])

    def _apply_poll_interval(self) -> None:
        """Pick the interval for the next poll from the time of day.

        DataUpdateCoordinator reads `update_interval` when it schedules the next
        refresh, which happens after this one finishes, so setting it here takes
        effect from the next tick onwards.
        """
        options = self.entry.options
        day = options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        night = options.get(CONF_NIGHT_POLL_INTERVAL, DEFAULT_NIGHT_POLL_INTERVAL)
        minutes = next_poll_minutes(
            dt_util.now(),
            day,
            night,
            parse_clock(options.get(CONF_NIGHT_START), DEFAULT_NIGHT_START),
            parse_clock(options.get(CONF_NIGHT_END), DEFAULT_NIGHT_END),
        )
        if self.update_interval != timedelta(minutes=minutes):
            _LOGGER.debug("Spond: next poll in %d minutes", minutes)
        self.update_interval = timedelta(minutes=minutes)

    async def _async_update_data(self) -> CoordinatorData:
        self._apply_poll_interval()
        await self._load_strings()
        tracked_members: list[dict] = self.entry.data.get(CONF_MEMBERS, [])
        canonical_names = {m["canonical"] for m in tracked_members}

        events_per_member: dict[str, list[dict]] = {m["canonical"]: [] for m in tracked_members}
        tasks_per_member: dict[str, dict[str, dict]] = {m["canonical"]: {} for m in tracked_members}
        # seen_uids deduplicates events that appear in multiple accounts for the same member
        seen_uids: dict[str, set[str]] = {m["canonical"]: set() for m in tracked_members}

        window_days = self.entry.options.get(CONF_EVENT_WINDOW_DAYS, DEFAULT_EVENT_WINDOW_DAYS)
        include_uninvited = self.entry.options.get(
            CONF_INCLUDE_UNINVITED, DEFAULT_INCLUDE_UNINVITED
        )
        # Never reach further for uninvited events than for confirmed ones: that
        # would put provisional events on dates where no confirmed event can
        # appear at all.
        uninvited_days = min(
            self.entry.options.get(CONF_UNINVITED_HORIZON_DAYS, DEFAULT_UNINVITED_HORIZON_DAYS),
            window_days,
        )

        # Confirmed events are few and cheap, so they get the full window. The
        # uninvited ones are the bulk of the payload and the least useful far
        # out, so they get a shorter one. With the option off this stays a
        # single request, exactly as before.
        fetches: list[tuple[str, int, bool]] = [("confirmed", window_days, False)]
        if include_uninvited:
            fetches.append(("uninvited", uninvited_days, True))

        accounts = self._get_accounts()
        any_success = False
        auth_failed: list[str] = []

        for acc in accounts:
            acc_username = acc[CONF_USERNAME]
            s = spond_lib.Spond(username=acc_username, password=acc[CONF_PASSWORD])
            try:
                now_utc = datetime.now(UTC)
                batches: list[list[dict]] = []
                for label, days, scheduled in fetches:
                    raw_events = await s.get_events(
                        min_end=now_utc,
                        max_end=now_utc + timedelta(days=days),
                        max_events=MAX_EVENTS,
                        # Off by default in the library "for performance
                        # reasons", which quietly hides every event whose
                        # invitation has not been sent — most of a season.
                        include_scheduled=scheduled,
                    )
                    _LOGGER.debug(
                        "Spond[%s]: %s fetch over %d days returned %d events",
                        acc_username,
                        label,
                        days,
                        len(raw_events),
                    )
                    if len(raw_events) >= MAX_EVENTS:
                        _LOGGER.warning(
                            "Spond[%s]: the %s fetch hit the %d-event ceiling, so events "
                            "near the end of its %d-day window are missing. Shorten the "
                            "window in the integration options.",
                            acc_username,
                            label,
                            MAX_EVENTS,
                            days,
                        )
                    batches.append(raw_events)
                any_success = True
            except Exception as e:
                err = str(e).lower()
                if any(
                    code in err for code in ("401", "403", "unauthorized", "forbidden", "invalid")
                ):
                    _LOGGER.warning("Spond[%s]: authentication failed", acc_username)
                    auth_failed.append(acc_username)
                else:
                    _LOGGER.error(
                        "Spond[%s] fetch error: %r\n%s", acc_username, e, traceback.format_exc()
                    )
                continue  # try remaining accounts
            finally:
                with contextlib.suppress(Exception):
                    await s.clientsession.close()

            # seen_uids dedupes the overlap between the two fetches, exactly as
            # it already dedupes an event shared by two accounts.
            for raw_events in batches:
                process_raw_events(
                    raw_events,
                    canonical_names,
                    seen_uids,
                    events_per_member,
                    tasks_per_member,
                    account=acc_username,
                    now=now_utc,
                )

        if not any_success and accounts:
            if auth_failed and len(auth_failed) == len(accounts):
                raise ConfigEntryAuthFailed(f"Authentication failed for: {', '.join(auth_failed)}")
            if self.last_update_success:
                _LOGGER.warning(
                    "Spond Tracker: all accounts unavailable, integration is now unavailable"
                )
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                async_create_issue(
                    self.hass,
                    DOMAIN,
                    "cannot_connect",
                    is_fixable=False,
                    severity=IssueSeverity.WARNING,
                    translation_key="cannot_connect",
                )
            raise UpdateFailed("All Spond accounts failed to fetch events")

        self._consecutive_failures = 0
        async_delete_issue(self.hass, DOMAIN, "cannot_connect")
        if not self.last_update_success:
            _LOGGER.info("Spond Tracker: integration is now available again")

        # Sort by start time
        for canonical in events_per_member:
            events_per_member[canonical].sort(key=lambda e: e.get("start") or "")

        tasks_data: dict[str, list[dict]] = {
            canonical: sorted(task_dict.values(), key=lambda t: t.get("start") or "")
            for canonical, task_dict in tasks_per_member.items()
        }
        self._apply_snoozes(tasks_data)

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
                        task_states = {
                            t.get("name"): t.get("status")
                            for t in (e.get("my_tasks") or [])
                            if isinstance(t, dict)
                        }
                        for task in cur_tasks - prev_tasks:
                            self.hass.bus.async_fire(
                                "spond_task_assigned",
                                {
                                    "member": canonical,
                                    "title": e.get("title"),
                                    "start": e.get("start"),
                                    "task": task,
                                    "status": task_states.get(task),
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

    # ── Snoozing ─────────────────────────────────────────────────────────────

    async def async_load_snoozes(self) -> None:
        """Restore snoozes from disk. Call before the first refresh."""
        stored = await self._snooze_store.async_load()
        self.snoozed = dict(stored) if isinstance(stored, dict) else {}

    def _apply_snoozes(self, tasks_data: dict[str, list[dict]]) -> None:
        """Stamp `snoozed_until` on tasks and forget snoozes that have run out.

        A snooze that has expired, or whose task has disappeared from Spond, is
        dropped so the store cannot grow without bound.
        """
        now = dt_util.utcnow()
        live_uids = {t["task_uid_key"] for tasks in tasks_data.values() for t in tasks}
        kept: dict[str, str] = {}
        for uid, until in self.snoozed.items():
            parsed = dt_util.parse_datetime(until)
            if uid in live_uids and parsed and parsed > now:
                kept[uid] = until

        for tasks in tasks_data.values():
            for task in tasks:
                task["snoozed_until"] = kept.get(task["task_uid_key"])

        if kept != self.snoozed:
            self.snoozed = kept
            self._snooze_store.async_delay_save(lambda: self.snoozed, 1)

    async def async_snooze_task(self, canonical: str, task_uid: str, until: datetime) -> None:
        """Hush one task until `until`; a time in the past clears the snooze."""
        self._find_task(canonical, task_uid)  # raises if unknown
        if until <= dt_util.utcnow():
            self.snoozed.pop(task_uid, None)
        else:
            self.snoozed[task_uid] = until.isoformat()
        await self._snooze_store.async_save(self.snoozed)
        await self.async_request_refresh()

    # ── Responding ───────────────────────────────────────────────────────────

    def _find_task(self, canonical: str, task_uid: str) -> dict:
        """Look up one tracked task, or explain what is available instead."""
        tasks = (self.data.tasks.get(canonical, []) if self.data else []) or []
        for task in tasks:
            if task["task_uid_key"] == task_uid:
                return task
        raise HomeAssistantError(
            f"No Spond task '{task_uid}' for member '{canonical}'. "
            f"Known tasks: {[t['task_uid_key'] for t in tasks] or 'none'}"
        )

    async def async_respond_to_task(self, canonical: str, task_uid: str, accepted: bool) -> None:
        """Accept or decline a task in Spond, then refresh.

        The response has to be sent through the same account the task was seen
        on: assignment ids are scoped to that account's view of the event.
        """
        task = self._find_task(canonical, task_uid)
        account = task.get("account")
        acc = next(
            (a for a in self._get_accounts() if a[CONF_USERNAME] == account),
            None,
        )
        if acc is None or not task.get("task_id") or not task.get("member_id"):
            raise HomeAssistantError(
                f"Task '{task_uid}' cannot be answered: it is missing the account or "
                "ids needed to reach Spond. Wait for the next poll and try again."
            )

        s = spond_lib.Spond(username=acc[CONF_USERNAME], password=acc[CONF_PASSWORD])
        try:
            await s.login()
            url = (
                f"{s.api_url}sponds/{task['event_uid']}"
                f"/tasks/{task['task_id']}/assignments/{task['member_id']}"
            )
            async with s.clientsession.put(
                url, headers=s.auth_headers, json={"accepted": accepted}
            ) as r:
                if r.status != 200:
                    body = (await r.text())[:200]
                    raise HomeAssistantError(
                        f"Spond rejected the response to '{task['task_name']}' "
                        f"(HTTP {r.status}): {body}"
                    )
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(
                f"Could not reach Spond to answer '{task['task_name']}': {err}"
            ) from err
        finally:
            with contextlib.suppress(Exception):
                await s.clientsession.close()

        _LOGGER.info(
            "Spond task '%s' for %s set to %s",
            task["task_name"],
            canonical,
            "accepted" if accepted else "declined",
        )
        # Answering settles the question, so any snooze on it is moot.
        if self.snoozed.pop(task_uid, None) is not None:
            await self._snooze_store.async_save(self.snoozed)
        await self.async_request_refresh()
