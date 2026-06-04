# Spond Tracker for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Latest release](https://img.shields.io/github/v/release/agjendem/ha-spond-tracker?display_name=tag&sort=semver)](https://github.com/agjendem/ha-spond-tracker/releases)
[![Validate](https://github.com/agjendem/ha-spond-tracker/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/agjendem/ha-spond-tracker/actions/workflows/validate.yml)
[![Lint](https://github.com/agjendem/ha-spond-tracker/actions/workflows/lint.yml/badge.svg?branch=main)](https://github.com/agjendem/ha-spond-tracker/actions/workflows/lint.yml)
[![License: MIT](https://img.shields.io/github/license/agjendem/ha-spond-tracker)](./LICENSE)

A native Home Assistant integration that syncs [Spond](https://www.spond.com/)
events and tasks — one calendar per tracked member, per-member sensors, and
real-time events on the HA event bus.

Built for households where one or more Spond accounts cover overlapping group
members. Events are deduplicated across accounts and matched to the right
member by first name.

## Features

- **Per-member calendars** — one calendar entity per tracked member showing
  upcoming Spond events with status, location, and task details.
- **Task events** — tasks assigned to a member appear as separate calendar
  entries (`📋` prefix) at the event's start time.
- **Multi-account** — add multiple Spond accounts; events are deduplicated
  across them automatically.
- **Status-aware** — accepted / declined / unanswered / waitinglist /
  cancelled shown as emoji prefixes. Declined events are hidden from the
  calendar. Cancelled events stay visible with a `🚫` prefix.
- **Per-member sensors** — event count for today and task count, with full
  detail in attributes.
- **HA event bus** — fires `spond_event_added`, `spond_event_removed`,
  `spond_event_changed`, `spond_event_cancelled`, and `spond_task_assigned`
  between polls. Use these to drive notifications and automations.
- **Localization** — calendar text and sensor names in English (default) or
  Norwegian Bokmål (`nb`). Follows your HA language setting automatically.

## Installation

### Via HACS (recommended)

1. HACS → menu (top right) → **Custom repositories**
2. URL: `https://github.com/agjendem/ha-spond-tracker`, Category: **Integration**
3. **ADD**, then find *Spond Tracker* in the Integration list → **Download**
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration → Spond Tracker**
   and follow the setup wizard.

### Manual

Copy `custom_components/spond_tracker/` into your HA config directory under
`custom_components/`. Restart Home Assistant, then add the integration via UI.

## Prerequisites

- Home Assistant 2023.11 or newer
- One or more Spond accounts

## Configuration

Setup is fully UI-based. The wizard walks through:

1. **Credentials** — Spond username (email) and password.
2. **Members** — multi-select which family members to track. Members are
   discovered from your Spond events automatically; one entry per first name.

After setup, go to **Options** to:
- Change the poll interval (default 30 minutes, range 5–1440).
- Add a second (or third) Spond account.
- Remove an account.

## What gets created

### Calendars

One `calendar.<member>` entity per tracked member. Each entry shows:
- **Summary**: `{emoji} {event title}` — emoji reflects the RSVP status
- **Description**: status, location, address, your tasks, full task list
- **Task entries**: `📋 {task name} — {event title}` at the event's start time

### Sensors

| Sensor | State | Attributes |
|--------|-------|------------|
| `sensor.spond_<member>` | Events today (int) | `today_events`, `next_event`, `upcoming_events` |
| `sensor.spond_<member>_tasks` | Active tasks (int) | `tasks` list with event, time, co-assignees |

### Event bus

| Event | Fired when | Key fields |
|-------|-----------|------------|
| `spond_event_added` | New event appears between polls | `member`, `title`, `start`, `status`, `uid` |
| `spond_event_removed` | Event disappears | `member`, `title`, `start`, `uid` |
| `spond_event_changed` | Field changed (title, time, location, status) | `member`, `title`, `start`, `changed_fields`, `uid` |
| `spond_event_cancelled` | Event flipped to cancelled | `member`, `title`, `start`, `location`, `uid` |
| `spond_task_assigned` | New task assigned to member | `member`, `title`, `start`, `task`, `uid` |

`member` is the lowercased first name (e.g. `alice`).

### Example automation

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

## Automation blueprints

The repo ships four blueprints that turn event-bus events into mobile
notifications without writing automation YAML. Import via the badges below:

[![Import: new task](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fagjendem%2Fha-spond-tracker%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fspond_new_task.yaml) **new task**

[![Import: event cancelled](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fagjendem%2Fha-spond-tracker%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fspond_event_cancelled.yaml) **event cancelled**

[![Import: event changed](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fagjendem%2Fha-spond-tracker%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fspond_event_changed.yaml) **event changed**

[![Import: task reminder](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fagjendem%2Fha-spond-tracker%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fspond_task_reminder.yaml) **task reminder (N min before task)**

## Troubleshooting

- **No events appearing** — check HA logs (Settings → System → Logs) for
  errors under the `spond_tracker` domain. The integration logs each poll.
- **Wrong member matched** — matching uses the first token of the Spond
  first name (lowercased). Two members with the same first name will
  collide; there is no workaround for that today.
- **Entities unavailable** — the coordinator marks all entities unavailable
  when every configured account fails to fetch. Check credentials in Options.
- **Poll not running** — the poll interval is configurable in Options
  (Settings → Devices & Services → Spond Tracker → Configure).

## Removing the integration

1. **Settings → Devices & Services → Spond Tracker**
2. Click the three-dot menu → **Delete**
3. Confirm. HA unloads all entities automatically.

## Development

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
pytest
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for commit conventions and the
release workflow.

## License

MIT — see [LICENSE](./LICENSE).

## Acknowledgements

Built on top of [Olen/Spond](https://github.com/Olen/Spond) — the
unofficial Spond Python client.
