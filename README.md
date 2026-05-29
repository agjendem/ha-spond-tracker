# Spond Tracker for Home Assistant (AppDaemon)

An [AppDaemon](https://appdaemon.readthedocs.io/) app that syncs
[Spond](https://www.spond.com/) events and tasks into Home Assistant —
one local calendar per family member, plus per-member sensors and
real-time events on the HA event bus.

Built for households where multiple parents have Spond accounts and
multiple children participate in groups. Events are de-duplicated across
parent accounts and mapped to the right child via Spond's
`behalfOfIds` field.

## Features

- **Per-member local calendars**: one `.ics` file per family member,
  written into a `local_calendar` config entry you control. Past events
  are preserved; future events are replaced wholesale each poll.
- **Multi-account aggregation**: log in with both parents' Spond
  accounts and the app de-duplicates events across them.
- **Status-aware**: accepted / declined / unanswered / waitinglist /
  cancelled — shown as emoji prefixes in the calendar `SUMMARY` and
  filtered from "events today"-counts. Declined events are filtered out
  of the calendar entirely.
- **Tasks as separate calendar events**: tasks assigned to you appear as
  their own `VEVENT` with a `📋` prefix at the start-time of the parent
  event.
- **Cancelled events** are shown with `🚫 AVLYST:` prefix in the
  calendar (so you keep historical context) but excluded from "today"
  counts.
- **HA event bus integration**: fires events when Spond state changes
  between polls — `spond_event_added`, `spond_event_removed`,
  `spond_event_changed`, `spond_event_cancelled`, `spond_task_assigned`.
  Use these to drive notifications, automations, etc.
- **Polling schedule**: hourly 06–14, every 30 min 15–22:30, idle
  overnight (configurable in code).

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
- One `local_calendar` integration *per family member* you want to
  track. Add via Settings → Devices & Services → Add Integration →
  Local Calendar. Note the config entry ID of each one (see
  [Finding the config_entry_id](#finding-the-config_entry_id) below).
- Python dependency: [`spond`](https://pypi.org/project/spond/) — add to
  AppDaemon's `python_packages` in the add-on configuration:
  ```yaml
  python_packages:
    - spond
  ```

## Configuration

### 1. Secrets

In `/config/secrets.yaml`, add one username/password pair per Spond
account you want to log in with:

```yaml
spond_parent_a_username: parent.a@example.com
spond_parent_a_password: hunter2
spond_parent_b_username: parent.b@example.com
spond_parent_b_password: hunter2
```

### 2. apps.yaml

In `/config/appdaemon/apps/apps.yaml` (create the file if it doesn't
exist), add:

```yaml
spond_tracker:
  module: spond_tracker
  class: SpondTracker
  accounts:
    - name: ParentA
      username: !secret spond_parent_a_username
      password: !secret spond_parent_a_password
    - name: ParentB
      username: !secret spond_parent_b_username
      password: !secret spond_parent_b_password
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
| `accounts[].name`  | yes      | Free-text label, used in logs.                                                                                                 |
| `accounts[].username` / `password` | yes | Spond credentials. **Reference via `!secret`** — never inline.                                                  |
| `members[].canonical` | yes   | Lowercase first name. Matched against the first word of Spond's `firstName` on memberships you can respond on-behalf-of.       |
| `members[].display_name` | yes | Used in sensor friendly names.                                                                                                |
| `members[].config_entry_id` | yes | ULID of the dedicated `local_calendar` config entry for this member.                                                       |

## What gets created

### Sensors (per member)

| Sensor                              | State              | Attributes                                            |
| ----------------------------------- | ------------------ | ----------------------------------------------------- |
| `sensor.spond_<canonical>`          | Events today (int) | `events`: list of today's events with title/time/etc. |
| `sensor.spond_<canonical>_oppgaver` | Open tasks (int)   | `tasks`: list of assigned tasks                       |

### Calendar entries

One `.ics` file per member. Each Spond event becomes a `VEVENT` with:
- `SUMMARY`: `{status-emoji} {title}` (or `🚫 AVLYST: {title}` if
  cancelled, `📋 {task-name}` for tasks)
- `DESCRIPTION`: status text, location, co-assignees, your task list
- `LOCATION`, `DTSTART`, `DTEND` as expected

### Event bus

Real-time events you can use as automation triggers:

| Event                    | Fired when                                                          | Data fields                                     |
| ------------------------ | ------------------------------------------------------------------- | ----------------------------------------------- |
| `spond_event_added`      | A new event appears for a member between polls                      | `canonical`, `title`, `start`, `end`, ...        |
| `spond_event_removed`    | An event you previously saw is gone (excl. cancellations)           | `canonical`, `title`                            |
| `spond_event_changed`    | A field changed (title, start, end, location)                       | `canonical`, `title`, `changed_fields`          |
| `spond_event_cancelled`  | An event flipped to cancelled                                       | `canonical`, `title`, `start`                   |
| `spond_task_assigned`    | A new task was assigned to a member                                 | `canonical`, `task_name`, `event_title`         |

### Example automation: ping me when I get a new task

```yaml
alias: "Spond: ny oppgave tildelt"
trigger:
  - platform: event
    event_type: spond_task_assigned
    event_data:
      canonical: alice
action:
  - service: notify.mobile_app_alice_phone
    data:
      title: "Ny Spond-oppgave"
      message: "{{ trigger.event.data.task_name }} ({{ trigger.event.data.event_title }})"
```

## Polling schedule

Hard-coded in `initialize()`:

- **06:00–14:00**: every full hour
- **15:00–22:30**: every full and half hour
- **23:00–06:00**: idle

To change, edit `initialize()` in `spond_tracker.py`. Spond's API is
not rate-limited aggressively but be a good citizen.

## Timezone

The app currently assumes `Europe/Oslo` (hard-coded). If you're in
another timezone, change `TZ = ZoneInfo("Europe/Oslo")` at the top of
`spond_tracker.py`. Patches to make this configurable are welcome.

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

## License

MIT — see [LICENSE](./LICENSE).

## Acknowledgements

Built on top of [Olen/Spond](https://github.com/Olen/Spond) — the
unofficial Spond Python client. All API quirks are theirs to discover;
all bugs in this wrapper are mine.
