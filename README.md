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

## Use cases

### Push notifications for tasks and events

The most common use case is sending a mobile push notification whenever
something changes in Spond — a new training is scheduled, a match is
cancelled, a time slot is updated, or a task is assigned. The integration
fires HA bus events between polls for all of these:

| Event | When |
|-------|------|
| `spond_event_added` | New training/match/event discovered |
| `spond_event_changed` | Title, time, location, or status changed |
| `spond_event_cancelled` | Event flipped to cancelled |
| `spond_event_removed` | Event disappeared entirely |
| `spond_task_assigned` | A duty/task assigned to the member |

The four importable blueprints in this repo cover the most common
scenarios out of the box (see [Automation blueprints](#automation-blueprints)).
For custom logic you can target any event directly:

```yaml
alias: "Spond: varsle om avlyst trening (Alice)"
trigger:
  - platform: event
    event_type: spond_event_cancelled
    event_data:
      member: alice
action:
  - service: notify.mobile_app_alice_phone
    data:
      title: "Trening avlyst ❌"
      message: >
        {{ trigger.event.data.title }}
        ({{ trigger.event.data.start | as_timestamp | timestamp_custom('%a %-d. %b %H:%M') }})
```

```yaml
alias: "Spond: varsle om ny trening (Alice)"
trigger:
  - platform: event
    event_type: spond_event_added
    event_data:
      member: alice
action:
  - service: notify.mobile_app_alice_phone
    data:
      title: "Ny Spond-aktivitet 📅"
      message: >
        {{ trigger.event.data.title }}
        {{ trigger.event.data.start | as_timestamp | timestamp_custom('%a %-d. %b %H:%M') }}
        {% if trigger.event.data.location %} — {{ trigger.event.data.location }}{% endif %}
```

```yaml
alias: "Spond: varsle om ny oppgave (Alice)"
trigger:
  - platform: event
    event_type: spond_task_assigned
    event_data:
      member: alice
action:
  - service: notify.mobile_app_alice_phone
    data:
      title: "Ny Spond-oppgave 📋"
      message: >
        {{ trigger.event.data.task }}
        på {{ trigger.event.data.title }}
        ({{ trigger.event.data.start | as_timestamp | timestamp_custom('%a %-d. %b %H:%M') }})
```

Repeat each automation per family member with their own notification target.

### Daily activity overview

Each tracked member has a `sensor.spond_<member>` with today's event count
and a full `calendar.spond_<member>` entity. Combine these in a morning
briefing — either as a dashboard card or as a spoken/text notification sent
at a fixed time each day.

**Template sensor — today's events as a text summary:**

```yaml
template:
  - sensor:
      - name: "Alice Spond i dag"
        state: "{{ state_attr('sensor.spond_alice', 'today_count') }} aktivitet(er)"
        attributes:
          summary: >
            {% set evs = state_attr('sensor.spond_alice', 'today_events') %}
            {% if evs %}
              {% for e in evs %}
                {{ e.title }} kl. {{ e.start | as_timestamp | timestamp_custom('%H:%M') }}
                ({{ e.status }}){{ '\n' if not loop.last }}
              {% endfor %}
            {% else %}
              Ingen aktiviteter i dag.
            {% endif %}
```

**Morning notification — sent at 07:00:**

```yaml
alias: "Spond: god morgen-oppsummering"
trigger:
  - platform: time
    at: "07:00:00"
action:
  - service: notify.mobile_app_family_group
    data:
      title: "Spond i dag"
      message: >
        {% for member in ['alice', 'bob'] %}
          {% set s = 'sensor.spond_' ~ member %}
          {% set n = state_attr(s, 'today_count') | int(0) %}
          {% if n > 0 %}
            {{ member | title }}: {{ n }} aktivitet(er)
            {% for e in state_attr(s, 'today_events') %}
              • {{ e.title }} {{ e.start | as_timestamp | timestamp_custom('%H:%M') }}
            {% endfor %}
          {% endif %}
        {% endfor %}
```

**Dashboard card** — use the `calendar` card and add `calendar.spond_alice`,
`calendar.spond_bob`, etc. as sources. You get a shared family activity view
directly on your Home Assistant dashboard, including tasks as separate entries.

## Data updates

The integration polls Spond once every **30 minutes** by default. You can
change the interval in **Options** (Settings → Devices & Services →
Spond Tracker → Configure) to any value between 5 and 1440 minutes.

Each poll fetches events starting from now and up to 60 days ahead (max 200
events per account). Calendar entities and sensors are refreshed immediately
after a successful poll. If a poll fails, the previous data remains available
and entities stay in their last-known state; if all accounts fail, entities
are marked unavailable and a warning is logged.

Change detection runs after every poll and fires HA bus events for any
additions, removals, or changes since the previous poll.

## Known limitations

- **Same first name** — member matching uses the first token of the Spond
  first name (lowercased). Two group members with the same first name will
  collide and share a single tracked member. There is no workaround within
  the integration today.
- **60-day window** — only events starting within the next 60 days are
  fetched. Events further in the future will not appear in the calendar.
- **Poll-based change detection** — event bus events (`spond_event_added`,
  etc.) are fired between polls, not in real time. Expect up to one
  poll-interval of delay.
- **Spond API** — this integration uses the unofficial Spond Python client
  (`Olen/Spond`). Spond has no public API, so breaking changes in the app
  backend may require an update to the library.

## Recorder / history

Sensor attributes (`today_events`, `upcoming_events`, `tasks`) contain full
event dicts and grow with the number of events. If you don't need history for
these attributes, exclude them in `configuration.yaml` to keep your database
small:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.spond_*
```

To keep the numeric state but skip the large attributes, use
`exclude_attributes` (available in HA 2024.2+).

## Troubleshooting

- **No events appearing** — check HA logs (Settings → System → Logs) for
  errors under the `spond_tracker` domain. The integration logs each poll.
- **Entities unavailable** — the coordinator marks all entities unavailable
  when every configured account fails to fetch. Check credentials in Options.
  The integration logs a warning when this happens and an info message when it
  recovers.
- **Poll not running** — the poll interval is configurable in Options
  (Settings → Devices & Services → Spond Tracker → Configure).
- **Member name collision** — see [Known limitations](#known-limitations).

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
