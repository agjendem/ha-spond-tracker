# Spond Tracker for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Latest release](https://img.shields.io/github/v/release/agjendem/ha-spond-tracker?display_name=tag&sort=semver)](https://github.com/agjendem/ha-spond-tracker/releases)
[![Validate](https://github.com/agjendem/ha-spond-tracker/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/agjendem/ha-spond-tracker/actions/workflows/validate.yml)
[![Lint](https://github.com/agjendem/ha-spond-tracker/actions/workflows/lint.yml/badge.svg?branch=main)](https://github.com/agjendem/ha-spond-tracker/actions/workflows/lint.yml)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](./LICENSE)

> **Unofficial integration** — not affiliated with or endorsed by [Spond](https://spond.com).

A native Home Assistant integration that syncs [Spond](https://spond.com)
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
- **Unsent invitations** — optionally include events whose invitation has not
  gone out yet, marked `🕗 (Title)` so they read as provisional rather than as
  something you have failed to answer. Off by default; see
  [Showing unsent invitations](#showing-unsent-invitations).
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

- Home Assistant 2026.3 or newer (runs on Python 3.14)
- One or more [Spond](https://spond.com) accounts

## Configuration

Setup is fully UI-based. The wizard walks through:

1. **Credentials** — Spond username (email or phone number) and password.
2. **Members** — multi-select which family members to track. Members are
   discovered from your Spond events automatically; one entry per first name.

After setup, go to **Options** to:
- Change the poll interval (default 30 minutes, range 5–1440).
- **Manage tracked members** — re-checks every configured account and lets you
  tick members on or off. Use this when someone was missing at setup time:
  members are only discovered from upcoming events, so anyone whose season had
  not started yet was never offered. Members already tracked stay on the list
  even when they currently have no events, and unticking one removes its
  calendar, sensors, and device.
- **Show events whose invitation has not been sent yet** — off by default; see
  below.
- **Days ahead to fetch events** — default 60.
- **Days ahead to look for unsent invitations** — default 14, never more than
  the window above.
- Add a second (or third) Spond account.
- Remove an account.

### Showing unsent invitations

Clubs usually create a whole season at once and let Spond send each invitation
a few days before the event. Until that moment Spond hides the event from the
API unless it is explicitly asked for, so by default a calendar only reaches a
few days into the future — the rest of the season exists but is invisible.

Turning this option on asks for those events too. Expect a much larger
response: a typical account returns roughly 20 events over 60 days without
them and roughly 170 with them, which is why the option is off by default.

Spond embeds the full recipient list — every player plus their guardians — in
each event, so one event weighs about 24 KB and how far ahead you look is the
main thing that decides how much gets downloaded. Measured across two accounts:

| Window | Events | Downloaded |
|---|---|---|
| 7 days | 49 | 1.0 MB |
| 14 days | 94 | 2.1 MB |
| 30 days | 208 | 4.6 MB |
| 60 days | 315 | 7.6 MB |

So the two horizons are separate settings. Confirmed events are few and cheap
and worth having far ahead — a tournament two months out belongs in the
calendar. Uninvited ones are the bulk of the payload and the least useful far
out: nothing can be answered yet and the plans still change. With the option on
the integration therefore makes two requests per account, one for confirmed
events over the full window and one for everything over the shorter horizon:

| Strategy | Downloaded | Confirmed events reach |
|---|---|---|
| Everything over 60 days | 7.6 MB | 60 days |
| Everything over 14 days | 2.1 MB | 14 days |
| **60-day window, 14-day horizon** (default) | **3.2 MB** | **60 days** |

Shortening only the horizon costs no tasks in practice — assignments land days,
not months, before the event.

Once an event is included, it needs distinguishing. Spond keeps everyone in
`unansweredIds` until the invitation goes out, so a not-yet-announced event is
reported exactly like one you have been ignoring. This integration gives it a
status of its own, `not_invited`:

- Calendar summary reads `🕗 (Training)` rather than `❓ Training`.
- The description says when the invitation is due to go out.
- Event attributes carry `invited: false` and `invite_time`, and the events
  sensor exposes `not_invited_count`.
- The moment the invitation is sent, the event switches to `unanswered` on the
  next poll and fires `spond_event_changed` with `invited` among the changed
  fields — a clean trigger for "you can answer this now" notifications.

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
| `sensor.spond_<member>_tasks` | Active tasks (int) | `tasks` list with event, time, co-assignees, `status`, `task_type`, `adults_only` |

Tasks on an event whose invitation is still unsent carry `invited: false` and
`invite_time`, and their calendar entry is parenthesised the same way.

A task's `status` is `accepted`, `unanswered`, or `declined` — Spond asks named people and waits for an answer. Declined tasks are excluded from the count and the attribute list; an unanswered one is still counted, because that is exactly the task that needs chasing.

### Event bus

| Event | Fired when | Key fields |
|-------|-----------|------------|
| `spond_event_added` | New event appears between polls | `member`, `title`, `start`, `status`, `uid` |
| `spond_event_removed` | Event disappears | `member`, `title`, `start`, `uid` |
| `spond_event_changed` | Field changed (title, time, location, status) | `member`, `title`, `start`, `changed_fields`, `uid` |
| `spond_event_cancelled` | Event flipped to cancelled | `member`, `title`, `start`, `location`, `uid` |
| `spond_task_assigned` | New task assigned to member | `member`, `title`, `start`, `task`, `status`, `uid` |

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

## Actions

| Action | What it does |
|--------|--------------|
| `spond_tracker.respond_to_task` | Accepts or declines a task in Spond on behalf of the targeted member. |
| `spond_tracker.snooze_task` | Hides a task from the sensor count for a while, without answering it. |

Both take a `task` uid, which every entry in the tasks sensor's `tasks`
attribute carries as `uid`. Target any entity belonging to the member — the
tasks sensor is the natural choice.

```yaml
action: spond_tracker.respond_to_task
target:
  entity_id: sensor.spond_alice_tasks
data:
  task: "1A2B3C::Drive the ice resurfacer"
  response: accept        # or: decline
```

Snoozing is a Home Assistant idea, not a Spond one: Spond knows only accepted,
declined and unanswered, so "ask me later" is remembered on this side. A
snoozed task drops out of the sensor's state but stays in the `tasks`
attribute with a `snoozed_until` timestamp, and reappears when the snooze runs
out. Answering a task clears any snooze on it.

```yaml
action: spond_tracker.snooze_task
target:
  entity_id: sensor.spond_alice_tasks
data:
  task: "1A2B3C::Drive the ice resurfacer"
  duration: "04:00:00"    # or: until: "2026-08-30 18:00:00"
```

Give neither `duration` nor `until` and the task stays quiet for 24 hours. A
`duration` of `0` clears an existing snooze.

Pair them with an actionable notification to answer a duty from your phone:

```yaml
alias: "Spond: ask about unanswered tasks"
triggers:
  - trigger: event
    event_type: spond_task_assigned
    event_data:
      member: alice
      status: unanswered
actions:
  - action: notify.mobile_app_alice_phone
    data:
      message: "{{ trigger.event.data.task }} — {{ trigger.event.data.title }}"
      data:
        actions:
          - action: SPOND_ACCEPT
            title: Accept
          - action: SPOND_SNOOZE
            title: Later
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
alias: "Spond: notify cancelled event (Alice)"
trigger:
  - platform: event
    event_type: spond_event_cancelled
    event_data:
      member: alice
action:
  - service: notify.mobile_app_alice_phone
    data:
      title: "Event cancelled ❌"
      message: >
        {{ trigger.event.data.title }}
        ({{ trigger.event.data.start | as_timestamp | timestamp_custom('%a %b %-d %H:%M') }})
```

```yaml
alias: "Spond: notify new event (Alice)"
trigger:
  - platform: event
    event_type: spond_event_added
    event_data:
      member: alice
action:
  - service: notify.mobile_app_alice_phone
    data:
      title: "New Spond event 📅"
      message: >
        {{ trigger.event.data.title }}
        {{ trigger.event.data.start | as_timestamp | timestamp_custom('%a %b %-d %H:%M') }}
        {% if trigger.event.data.location %} — {{ trigger.event.data.location }}{% endif %}
```

```yaml
alias: "Spond: notify new task (Alice)"
trigger:
  - platform: event
    event_type: spond_task_assigned
    event_data:
      member: alice
action:
  - service: notify.mobile_app_alice_phone
    data:
      title: "New Spond task 📋"
      message: >
        {{ trigger.event.data.task }}
        for {{ trigger.event.data.title }}
        ({{ trigger.event.data.start | as_timestamp | timestamp_custom('%a %b %-d %H:%M') }})
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
      - name: "Alice Spond today"
        state: "{{ state_attr('sensor.spond_alice', 'today_count') }} event(s)"
        attributes:
          summary: >
            {% set evs = state_attr('sensor.spond_alice', 'today_events') %}
            {% if evs %}
              {% for e in evs %}
                {{ e.title }} at {{ e.start | as_timestamp | timestamp_custom('%H:%M') }}
                ({{ e.status }}){{ '\n' if not loop.last }}
              {% endfor %}
            {% else %}
              No events today.
            {% endif %}
```

**Morning notification — sent at 07:00:**

```yaml
alias: "Spond: morning summary"
trigger:
  - platform: time
    at: "07:00:00"
action:
  - service: notify.mobile_app_family_group
    data:
      title: "Spond today"
      message: >
        {% for member in ['alice', 'bob'] %}
          {% set s = 'sensor.spond_' ~ member %}
          {% set n = state_attr(s, 'today_count') | int(0) %}
          {% if n > 0 %}
            {{ member | title }}: {{ n }} event(s)
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

- **Same first name across your own tracked members** — the first token of
  the Spond first name (lowercased) is the key that groups one person across
  groups and accounts, so two *tracked* people sharing a first name would
  collapse into one. Strangers are unaffected: everyone else is matched by
  member id, so three people called Alice in one group cannot take each
  other's tasks.
- **Members are discovered from events** — someone with no upcoming events is
  invisible to Spond's API, so they cannot be offered at setup. Re-run
  **Options → Manage tracked members** once their season starts.
- **Fetch window** — only events starting within the window are fetched
  (60 days by default, configurable). Events beyond it will not appear in the
  calendar.
- **Unsent invitations are opt-in** — with the option off, events only become
  visible once their invitation is sent, which for many clubs is a few days
  before they happen.
- **Poll-based change detection** — event bus events (`spond_event_added`,
  etc.) are fired between polls, not in real time. Expect up to one
  poll-interval of delay.
- **Spond API** — this integration uses the unofficial [Olen/Spond](https://github.com/Olen/Spond) Python client.
  Spond has no public API, so breaking changes in the app
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

Requires **Python 3.13+** (the test suite targets HA 2026.x).

```bash
git clone https://github.com/agjendem/ha-spond-tracker.git
cd ha-spond-tracker
python3.13 -m venv .venv
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

GPL-3.0 — see [LICENSE](./LICENSE). This project depends on
[Olen/Spond](https://github.com/Olen/Spond) which is GPL-3.0, so the same
license applies here.

## Acknowledgements

Built on top of the unofficial [Olen/Spond](https://github.com/Olen/Spond) Python client.
