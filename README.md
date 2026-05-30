# Spond Tracker for Home Assistant (AppDaemon)

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Latest release](https://img.shields.io/github/v/release/agjendem/ha-spond-tracker?display_name=tag&sort=semver)](https://github.com/agjendem/ha-spond-tracker/releases)
[![Validate](https://github.com/agjendem/ha-spond-tracker/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/agjendem/ha-spond-tracker/actions/workflows/validate.yml)
[![Lint](https://github.com/agjendem/ha-spond-tracker/actions/workflows/lint.yml/badge.svg?branch=main)](https://github.com/agjendem/ha-spond-tracker/actions/workflows/lint.yml)
[![License: MIT](https://img.shields.io/github/license/agjendem/ha-spond-tracker)](./LICENSE)

An [AppDaemon](https://appdaemon.readthedocs.io/) app that syncs
[Spond](https://www.spond.com/) events and tasks into Home Assistant —
one local calendar per tracked member, plus per-member sensors and
real-time events on the HA event bus.

Built for setups where one or more Spond accounts cover overlapping
group members — typical examples include shared households, sports
clubs with multiple coaches, or staff at after-school programs. Events
are de-duplicated across accounts and mapped to the right tracked
member via Spond's `behalfOfIds` field.

## Features

- **Per-member local calendars**: one `.ics` file per tracked member,
  written into a `local_calendar` config entry you control. Past events
  are preserved; future events are replaced wholesale each poll.
- **Multi-account aggregation**: log in with one or more Spond accounts
  and the app de-duplicates events across them.
- **Status-aware**: accepted / declined / unanswered / waitinglist /
  cancelled — shown as emoji prefixes in the calendar `SUMMARY` and
  filtered from "events today"-counts. Declined events are filtered out
  of the calendar entirely.
- **Tasks as separate calendar events**: tasks assigned to you appear as
  their own `VEVENT` with a `📋` prefix at the start-time of the
  underlying event.
- **Cancelled events** are shown with `🚫 AVLYST:` prefix in the
  calendar (so you keep historical context) but excluded from "today"
  counts.
- **HA event bus integration**: fires events when Spond state changes
  between polls — `spond_event_added`, `spond_event_removed`,
  `spond_event_changed`, `spond_event_cancelled`, `spond_task_assigned`.
  Use these to drive notifications, automations, etc.
- **Polling schedule**: hourly 06–14, every 30 min 15–22:30, idle
  overnight (configurable in code).
- **Localization**: calendar text and sensor friendly names available
  in English (default) or Norwegian Bokmål via `language: en|nb` in
  apps.yaml. Translations live in `apps/spond_tracker/translations/`.

## Installation via HACS

1. **Add as custom repository**
   - HACS → menu (top right) → *Custom repositories*
   - URL: `https://github.com/agjendem/ha-spond-tracker`
   - Category: **AppDaemon**
   - Click **ADD**
2. **Install**
   - Find *Spond Tracker* in the HACS AppDaemon list → **Download**
   - HACS writes the code to `/config/appdaemon/apps/spond_tracker/`
3. **Configure** — see [Configuration](#configuration) below.
4. **Restart AppDaemon add-on** (or trigger an app reload).

### Private repository note

If you've forked or self-host this in a private repository, HACS needs a
[Personal Access Token (PAT)](https://github.com/settings/tokens) with
`repo` scope, set under HACS configuration (`token: ...`). Otherwise the
clone will fail silently.

## Prerequisites

- Home Assistant (any reasonably current version)
- The [AppDaemon 4 add-on](https://github.com/hassio-addons/addon-appdaemon)
  (or self-hosted AppDaemon ≥ 4.5)
- One `local_calendar` integration *per tracked member*. Add via
  Settings → Devices & Services → Add Integration →
  Local Calendar. Note the config entry ID of each one (see
  [Finding the config_entry_id](#finding-the-config_entry_id) below).
- Python dependency: [`spond`](https://pypi.org/project/spond/) at the
  pinned version below — add to AppDaemon's `python_packages` in the
  add-on configuration:
  ```yaml
  python_packages:
    - spond==1.2.1
  ```
  See `requirements.txt` for the canonical version pin used by this
  release. Newer minor versions may also work, but only the pinned
  version is tested.

## Configuration

### 1. Secrets

In `/config/secrets.yaml`, add one username/password pair per Spond
account you want to log in with:

```yaml
spond_account_a_username: account-a@example.com
spond_account_a_password: hunter2
spond_account_b_username: account-b@example.com
spond_account_b_password: hunter2
```

### 2. apps.yaml

In `/config/appdaemon/apps/apps.yaml` (create the file if it doesn't
exist), add:

```yaml
spond_tracker:
  module: spond_tracker
  class: SpondTracker
  language: en          # en (default) | nb
  timezone: Europe/Oslo # default; any IANA tz works (UTC, America/Los_Angeles, ...)
  accounts:
    - name: AccountA
      username: !secret spond_account_a_username
      password: !secret spond_account_a_password
    - name: AccountB
      username: !secret spond_account_b_username
      password: !secret spond_account_b_password
  members:
    - canonical: alice
      display_name: Alice
      config_entry_id: 01HXXXXXXXXXXXXXXXXXXXXXXX
    - canonical: bob
      display_name: Bob
      config_entry_id: 01HYYYYYYYYYYYYYYYYYYYYYYY
```

Full example: [`example-apps.yaml`](./example-apps.yaml).

### Finding the `config_entry_id`

1. Settings → Devices & Services → **Local Calendar**
2. Click the integration card. Each calendar shows as a sub-entry.
3. Click a calendar → the URL becomes something like
   `/config/integrations/integration/local_calendar#config_entry/01HXXXXXXXXXXXXXXXXXXXXXXX`
4. The 26-char ULID after `config_entry/` is what you want.

You need one `local_calendar` per member. The app writes to the
`.storage/local_calendar.<slug>.ics` file owned by that config entry,
then calls `homeassistant.reload_config_entry` to make HA re-read it.

### Field reference

| Field              | Required | Description                                                                                                                    |
| ------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `language`         | no       | `en` (default) or `nb` (Norwegian Bokmål). The legacy code `no` is accepted as an alias for `nb`. Controls calendar SUMMARY/DESCRIPTION text and sensor friendly names. Logs stay English. |
| `timezone`         | no       | IANA timezone name (e.g. `Europe/Oslo`, `America/Los_Angeles`, `UTC`). Default `Europe/Oslo`. Controls "today" cutoffs and the poll-schedule clock. Invalid names log a WARNING and fall back to the default. |
| `accounts[].name`  | yes      | Free-text label, used in logs.                                                                                                 |
| `accounts[].username` / `password` | yes | Spond credentials. **Reference via `!secret`** — never inline.                                                  |
| `members[].canonical` | yes   | Lowercase first name. Matched against the first word of Spond's `firstName` on memberships you can respond on-behalf-of.       |
| `members[].display_name` | yes | Used in sensor friendly names.                                                                                                |
| `members[].config_entry_id` | yes | ULID of the dedicated `local_calendar` config entry for this member.                                                       |

## What gets created

### Sensors (per member)

| Sensor                            | State              | Attributes                                            |
| --------------------------------- | ------------------ | ----------------------------------------------------- |
| `sensor.spond_<canonical>`        | Events today (int) | `today_events`, `next_event`, `upcoming_events`       |
| `sensor.spond_<canonical>_tasks`  | Open tasks (int)   | `tasks`: list of tasks assigned to this member        |

### Calendar entries

One `.ics` file per member. Each Spond event becomes a `VEVENT` with:
- `SUMMARY`: `{status-emoji} {title}` (or `🚫 AVLYST: {title}` if
  cancelled, `📋 {task-name}` for tasks)
- `DESCRIPTION`: status text, location, co-assignees, your task list
- `LOCATION`, `DTSTART`, `DTEND` as expected

### Event bus

Real-time events you can use as automation triggers:

| Event                    | Fired when                                                          | Data fields                                                        |
| ------------------------ | ------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `spond_event_added`      | A new event appears for a member between polls                      | `member`, `title`, `start`, `location`, `status`, `uid`            |
| `spond_event_removed`    | An event you previously saw is gone (excl. cancellations)           | `member`, `title`, `start`, `uid`                                  |
| `spond_event_changed`    | A field changed (title, start, end, location)                       | `member`, `title`, `start`, `status`, `changed_fields`, `uid`      |
| `spond_event_cancelled`  | An event flipped to cancelled                                       | `member`, `title`, `start`, `location`, `uid`                      |
| `spond_task_assigned`    | A new task was assigned to a member                                 | `member`, `title`, `start`, `task`, `uid`                          |

`member` is the `canonical` slug from your apps.yaml config (e.g. `alice`).

### Example automation: ping me when I get a new task

```yaml
alias: "Spond: new task assigned"
trigger:
  - platform: event
    event_type: spond_task_assigned
    event_data:
      member: alice
action:
  - service: notify.mobile_app_alice_phone
    data:
      title: "New Spond task"
      message: "{{ trigger.event.data.task }} ({{ trigger.event.data.title }})"
```

## Polling schedule

Hard-coded in `initialize()`:

- **06:00–14:00**: every full hour
- **15:00–22:30**: every full and half hour
- **23:00–06:00**: idle

To change, edit `initialize()` in `spond_tracker.py`. Spond's API is
not rate-limited aggressively but be a good citizen.

## Localization

User-facing text (calendar SUMMARY/DESCRIPTION and sensor friendly_name)
is loaded from JSON files in `apps/spond_tracker/translations/`. Set
`language: en` (default) or `language: nb` in apps.yaml. The legacy
code `no` is accepted as an alias for `nb` and will log a deprecation
warning at startup.

Lookup uses dotted paths (e.g. `calendar.location_label`,
`sensors.events_friendly`). Fallback chain on a missing key:
`<lang> → language-base (region stripped) → en`. If a key is missing in
all of them, the dotted identifier itself is returned so the gap is
visible rather than silently empty.

Log messages are always English and not localized.

### Adding a new language

1. Copy `translations/en.json` to `translations/<bcp47>.json`
   (e.g. `da.json`, `de.json`, `sv.json`).
2. Translate every string. Keys must match `en.json` exactly.
3. Open a PR — `validate.yml` will check that the JSON parses and that
   the call sites in `spond_tracker.py` still resolve.

## Timezone

The app uses the timezone configured in apps.yaml to decide the cutoff
between today and tomorrow (for `today_count` on the events sensor) and
to compute the local time the poll schedule fires at. ICS output is
always written in UTC per the calendar spec.

```yaml
spond_tracker:
  ...
  timezone: Europe/Oslo   # default if omitted
```

Any IANA timezone string works (`UTC`, `America/Los_Angeles`,
`Asia/Tokyo`, ...). An invalid name logs a WARNING at startup and falls
back to `Europe/Oslo` so the app still starts.

Note that the AppDaemon add-on also has its own `time_zone` setting in
`appdaemon.yaml`. Both are useful: the add-on setting controls
AppDaemon's internal scheduler reference, while this `timezone:` field
controls how `spond_tracker` interprets dates. Keep them in sync for
predictable behavior.

## Migrating from earlier versions

### `_oppgaver` → `_tasks` (entity_id rename)

The task-count sensor was renamed from
`sensor.spond_<canonical>_oppgaver` to `sensor.spond_<canonical>_tasks`
to use a language-neutral entity_id. After updating, the old `_oppgaver`
entity stays in the registry as a stale orphan with whatever state it
last had.

**Action required:**
1. Update any references in your dashboards, automations, scripts, or
   templates that read `sensor.spond_*_oppgaver`.
2. After the first poll on the new version, delete the old
   `sensor.spond_*_oppgaver` entries via Developer Tools → States →
   delete entity (or via the entity registry).

### `language: no` → `language: nb`

If you previously set `language: no` in `apps.yaml`, it still works but
emits a deprecation warning on startup. Change it to `language: nb`
(Norwegian Bokmål per BCP-47) at your convenience.

## Troubleshooting

- **No events appearing** — check AppDaemon logs (Settings → Add-ons →
  AppDaemon → Logs). The app logs each poll's success/failure.
- **Wrong member matched** — `canonical` matching is first-name
  prefix-match. If two members share a first name, you'll need to
  patch the matching logic.
- **Calendar empty after install** — the app needs at least one
  successful poll. It runs once 10 seconds after AppDaemon starts;
  give it ~30 seconds.
- **Sensor state stays at 0** — verify the member has an event today
  in Spond, that you've accepted/not-yet-responded, and that your
  account has visibility into the group.

## What is *not* stored in this repository

By design, this repo contains only generic application code. The
following are **never committed** and must be configured locally:

- `apps.yaml` (your account/member mapping — identifies you)
- `secrets.yaml` (credentials)
- `*.ics` files (calendar contents)

See `.gitignore`.

## Development

Local development uses a virtualenv with pinned tools:

```bash
git clone https://github.com/agjendem/ha-spond-tracker.git
cd ha-spond-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Run the same checks CI runs:

```bash
ruff check .
ruff format --check .
python -m json.tool apps/spond_tracker/translations/en.json > /dev/null
python -m json.tool apps/spond_tracker/translations/nb.json > /dev/null
python -m py_compile apps/spond_tracker/spond_tracker.py
```

Bumping a runtime dep (e.g. `spond`): update `requirements.txt`,
`README.md`, and `info.md` in a commit prefixed `deps:`. Bumping a dev
dep: update `requirements-dev.txt` and the workflow files, prefixed
`build:` or `ci:`.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/);
[`release-please`](https://github.com/googleapis/release-please) handles
version bumps, `CHANGELOG.md`, and GitHub releases automatically when
the release PR it opens is merged. See
[CONTRIBUTING.md](./CONTRIBUTING.md) for the full guide.

## License

MIT — see [LICENSE](./LICENSE).

## Acknowledgements

Built on top of [Olen/Spond](https://github.com/Olen/Spond) — the
unofficial Spond Python client. All API quirks are theirs to discover;
all bugs in this wrapper are mine.
