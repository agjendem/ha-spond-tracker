# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.12.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.11.0...v0.12.0) (2026-08-23)


### Features

* allow a longer polling interval overnight ([340de88](https://github.com/agjendem/ha-spond-tracker/commit/340de8881709e2c276f191388d5f306d23cf2eca))
* optionally include events whose invitation has not been sent ([8025867](https://github.com/agjendem/ha-spond-tracker/commit/8025867819808a83e187bbf7a79b472432b5fbea))
* split the fetch so uninvited events use a shorter horizon ([ddd7d34](https://github.com/agjendem/ha-spond-tracker/commit/ddd7d34e3c0925bd9518e7135493a1519b2b6fac))


### Documentation

* state fetch sizes as gzipped bytes on the wire ([db6751a](https://github.com/agjendem/ha-spond-tracker/commit/db6751a2316b6e8d080273c7f1f0dee0a15d947d))

## [0.11.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.10.0...v0.11.0) (2026-08-22)


### Features

* accept, decline and snooze Spond tasks from Home Assistant ([37b6d2c](https://github.com/agjendem/ha-spond-tracker/commit/37b6d2c676e676a90036fdd605aa96c8ccd46188))

## [0.10.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.9.0...v0.10.0) (2026-08-22)


### Features

* manage tracked members from the options flow ([e64f329](https://github.com/agjendem/ha-spond-tracker/commit/e64f32928c7978c08563c5053571bb41de524b3f))


### Bug Fixes

* match tasks by member id and parse Spond's real task schema ([#45](https://github.com/agjendem/ha-spond-tracker/issues/45)) ([97a6620](https://github.com/agjendem/ha-spond-tracker/commit/97a6620c66f2915883a9f8c4807d5db39c3fb3b7))


### Dependencies

* bump the pip-deps group with 2 updates ([fefcb46](https://github.com/agjendem/ha-spond-tracker/commit/fefcb4626a719a5488a9cce6a853066a8d4297ea))

## [0.9.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.8.2...v0.9.0) (2026-08-05)


### Features

* name devices "Spond - &lt;first name&gt;" ([a8c4b6e](https://github.com/agjendem/ha-spond-tracker/commit/a8c4b6edb321c58211f2301fd721f9611229427e))

## [0.8.2](https://github.com/agjendem/ha-spond-tracker/compare/v0.8.1...v0.8.2) (2026-08-05)


### Bug Fixes

* stop rendering the member name twice in entity names ([a85ca53](https://github.com/agjendem/ha-spond-tracker/commit/a85ca5344f0ff6be02b42303a412384aebe16feb))

## [0.8.1](https://github.com/agjendem/ha-spond-tracker/compare/v0.8.0...v0.8.1) (2026-08-05)


### Bug Fixes

* count multi-day events as happening on every day they span ([5ec1bfe](https://github.com/agjendem/ha-spond-tracker/commit/5ec1bfeada7284a3e84edfabfb2ede664d449b28))
* report the correct integration version in Home Assistant ([4c2dbc2](https://github.com/agjendem/ha-spond-tracker/commit/4c2dbc21cfc4cbeec2a3bda6fa9dc80c21d2f728))

## [0.8.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.7.2...v0.8.0) (2026-08-05)


### ⚠ BREAKING CHANGES

* Home Assistant 2026.3.0 or newer is now required. Installs on HA 2026.1.x-2026.2.x run Python 3.13 and can no longer load this integration.

### Features

* require Home Assistant 2026.3.0 and target Python 3.14 ([9295417](https://github.com/agjendem/ha-spond-tracker/commit/9295417e7e6122c4d7e8d5e662ac4152e11b1aee))

## [0.7.2](https://github.com/agjendem/ha-spond-tracker/compare/v0.7.1...v0.7.2) (2026-08-05)


### Dependencies

* bump the pip-deps group across 1 directory with 3 updates ([70b1e0c](https://github.com/agjendem/ha-spond-tracker/commit/70b1e0c4863fc0cf6e73d7c746fa208060485e28))

## [0.7.1](https://github.com/agjendem/ha-spond-tracker/compare/v0.7.0...v0.7.1) (2026-06-05)


### Documentation

* switch license to GPL-3.0, add unofficial disclaimer ([1e4dc28](https://github.com/agjendem/ha-spond-tracker/commit/1e4dc289ef77e9e81d6ce303cc648c149109bdbc))
* translate README examples to English and fix prerequisites ([acc0201](https://github.com/agjendem/ha-spond-tracker/commit/acc0201491731881a05dc357946e06b68bff677d))
* use static MIT badge instead of dynamic GitHub license badge ([2334e77](https://github.com/agjendem/ha-spond-tracker/commit/2334e776ec2cb17c7194e6d1a959c589f3d1d72b))

## [0.7.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.6.0...v0.7.0) (2026-06-04)


### Features

* bump quality_scale to gold in manifest ([a9288a7](https://github.com/agjendem/ha-spond-tracker/commit/a9288a72311cd918086ebea34f73bca4687ee118))

## [0.6.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.5.0...v0.6.0) (2026-06-04)


### Features

* brand icons at correct sizes, icon-translations, quality_scale silver ([639e5f4](https://github.com/agjendem/ha-spond-tracker/commit/639e5f424855b1e2c6cee1aff49b9a4ea9f630eb))
* repair-issues Gold IQS rule — persistent connection failure notification ([33d5b0c](https://github.com/agjendem/ha-spond-tracker/commit/33d5b0c2e1fb756cb98f93876fb40d75ed10ed07))


### Documentation

* add CLAUDE.md with full IQS checklist and project context ([f8b96f7](https://github.com/agjendem/ha-spond-tracker/commit/f8b96f7c055e63c50b90e58297ebe1a8feab0396))
* add use-cases section (Gold IQS docs-use-cases) ([2d25cda](https://github.com/agjendem/ha-spond-tracker/commit/2d25cda159bc1575a4891bc535c108321775c67c))
* mark Gold IQS complete in CLAUDE.md ([14505df](https://github.com/agjendem/ha-spond-tracker/commit/14505dfae7e33b74463654bf5d85045f132a9ad8))

## [0.5.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.4.0...v0.5.0) (2026-06-04)


### Features

* add config flow tests; fix OptionsFlow config_entry compat ([48b7f25](https://github.com/agjendem/ha-spond-tracker/commit/48b7f251f60301b98e6caf3f0b8927f4254b209d))
* add DeviceInfo to group entities per tracked member ([e780b63](https://github.com/agjendem/ha-spond-tracker/commit/e780b63e0882451d1df0cf0e63241ca0a9a65b01))
* add diagnostics platform and reconfiguration flow ([063a20c](https://github.com/agjendem/ha-spond-tracker/commit/063a20c3dd5684a5c934f8b313859e3e04352fd4))
* add native Home Assistant integration (custom_components) ([d926a59](https://github.com/agjendem/ha-spond-tracker/commit/d926a59976975db6c565a0cdfd15c79625f05b12))
* add reauthentication flow (Silver IQS) ([bf9d52f](https://github.com/agjendem/ha-spond-tracker/commit/bf9d52f097b57aa5eb5e6f832841e0bdf5cc9ac5))
* entity-translations, log-when-unavailable, and expanded test coverage ([fe08fef](https://github.com/agjendem/ha-spond-tracker/commit/fe08fef256f1dceeac3a78ba89cae8d7184f3c30))
* replace AppDaemon app with native HA integration ([f9714e7](https://github.com/agjendem/ha-spond-tracker/commit/f9714e77ce7392094b78528ae82a83fc0d586e4f))


### Bug Fixes

* add issue_tracker to manifest and local brand icon ([f233c86](https://github.com/agjendem/ha-spond-tracker/commit/f233c8688c43fa1c60c23f77d5c4469456a1a162))
* load translations async via executor, cache on coordinator ([dfe0d3d](https://github.com/agjendem/ha-spond-tracker/commit/dfe0d3d16e12a2bf2fe2caa611c39ad668803e71))
* resolve all ruff lint errors (unused imports, RUF012, RUF059) ([29d1202](https://github.com/agjendem/ha-spond-tracker/commit/29d12023e7ca32cf329fc1584525b58722c746d9))


### Documentation

* add recorder.exclude guidance for sensor attributes ([bbf9c01](https://github.com/agjendem/ha-spond-tracker/commit/bbf9c01a1a568c2227417e1e89fbc3517c260793))


### Refactoring

* remove AppDaemon-era ICS helpers and v1 legacy fallback ([b28df99](https://github.com/agjendem/ha-spond-tracker/commit/b28df9933715e60085eaa39296b453624ba79ce6))
* use entry.runtime_data, PARALLEL_UPDATES; add removal docs ([232bccf](https://github.com/agjendem/ha-spond-tracker/commit/232bccfb3be790d715491261fa7df3d2cd95a710))

## [0.4.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.3.0...v0.4.0) (2026-06-01)


### Features

* ship 4 automation blueprints for Spond events ([d9ac884](https://github.com/agjendem/ha-spond-tracker/commit/d9ac884b53ee00da47227213ef58e1893ceeb628))

## [0.3.0](https://github.com/agjendem/ha-spond-tracker/compare/v0.2.1...v0.3.0) (2026-05-31)


### Features

* configurable poll schedule via cron + colored status emoji ([7c1238f](https://github.com/agjendem/ha-spond-tracker/commit/7c1238f582b01a4e1f8b3e9418c8d4f55fc32c11))

## [0.2.1](https://github.com/agjendem/ha-spond-tracker/compare/v0.2.0...v0.2.1) (2026-05-30)


### Documentation

* add status badges to README ([1348c2f](https://github.com/agjendem/ha-spond-tracker/commit/1348c2fdde5e563c0043145df5c916ed3d9d073f))


### Refactoring

* split spond_tracker.py into helpers + i18n modules ([edba01a](https://github.com/agjendem/ha-spond-tracker/commit/edba01a74bf1a19204c0337657a57e3070c9c853))

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
