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
from .spond_helpers import event_fingerprint, process_raw_events
from .spond_i18n import TRANSLATIONS_DIR, load_translations

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
        self.strings: dict = {}
        self._strings_lang: str = ""

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

    async def _async_update_data(self) -> CoordinatorData:
        await self._load_strings()
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

            process_raw_events(
                raw_events, canonical_names, seen_uids, events_per_member, tasks_per_member
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
