# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.1.0...v0.2.0) (2026-05-30)


### Features

* make timezone configurable via apps.yaml ([639b676](https://github.com/agjendem/ha-spond-tracker/commit/639b676c408b1fd53201dbacede8620ab627bdca))

## [Unreleased]

## [0.1.0] - 2026-05-30

Initial public release.

### Added

- AppDaemon app `SpondTracker` that polls Spond on a fixed schedule
  (hourly 06–14, every 30 min 15–22:30, idle 23–06) and syncs events +
  tasks into Home Assistant.
- Per-tracked-member local calendar `.ics` output, written into a
  caller-supplied `local_calendar` config entry. Past events are
  preserved across polls; future events are replaced wholesale.
- Multi-account aggregation: log in with one or more Spond accounts and
  the app de-duplicates events per tracked member.
- Status-aware calendar output: emoji prefix in SUMMARY for accepted /
  declined / unanswered / waitinglist / cancelled events. Cancelled
  events show a localized `CANCELLED:` / `AVLYST:` prefix. Declined
  events are excluded from the calendar entirely.
- Task tracking: tasks assigned to a tracked member are written as
  dedicated VEVENTs (with a `📋` prefix) and aggregated into
  `sensor.spond_<canonical>_tasks` with full structured attributes.
- HA event-bus integration: `spond_event_added`, `spond_event_removed`,
  `spond_event_changed`, `spond_event_cancelled`, `spond_task_assigned`
  fire on poll-over-poll diffs, usable as automation triggers.
- Localization: user-facing text loaded from
  `apps/spond_tracker/translations/{en,nb}.json` with fallback chain
  `lang → language-base → en`. Set `language: en` (default) or
  `language: nb` in `apps.yaml`. The legacy code `no` is accepted as a
  deprecated alias for `nb`.
- HACS metadata: `hacs.json`, `info.md` for the install modal,
  `appdaemon` GitHub topic.
- CI: `validate.yml` runs `hacs/action` on push and PR; `lint.yml` runs
  `ruff` and JSON-validates each translation file.
- Runtime dep pin: `spond==1.2.1` documented in `requirements.txt`.
- Dev dep pin: `ruff==0.15.15` in `requirements-dev.txt`, matched by CI.

[Unreleased]: https://github.com/agjendem/ha-spond-tracker/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/agjendem/ha-spond-tracker/releases/tag/v0.1.0
