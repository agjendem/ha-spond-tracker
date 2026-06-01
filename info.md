# Spond Tracker

AppDaemon app that syncs [Spond](https://www.spond.com/) events and tasks
into Home Assistant — one local calendar per tracked member, plus
per-member sensors and event-bus integration for automations.

## What you get

- A `.ics` file per tracked member, written into a `local_calendar`
  integration you control. Past events are preserved as history.
- `sensor.spond_<member>` — number of events today, with upcoming list.
- `sensor.spond_<member>_tasks` — number of tasks assigned to that
  member, with full task details in attributes.
- HA event-bus events: `spond_event_added`, `spond_event_removed`,
  `spond_event_changed`, `spond_event_cancelled`, `spond_task_assigned`.

## Quick start

1. Install via HACS (this page).
2. Add `spond==1.2.1` to the AppDaemon add-on's `python_packages` list.
3. Create one `local_calendar` integration instance per tracked member.
4. Configure `/config/appdaemon/apps/apps.yaml`:
   ```yaml
   spond_tracker:
     module: spond_tracker
     class: SpondTracker
     language: en          # en (default) | nb
     timezone: Europe/Oslo # default; any IANA tz string works
     poll_schedules:       # default keeps the API quiet 23-06
       - "0 6-14 * * *"
       - "0,30 15-22 * * *"
     accounts:
       - name: AccountA
         username: !secret spond_account_a_username
         password: !secret spond_account_a_password
     members:
       - canonical: alice
         display_name: Alice
         config_entry_id: 01HXXXXXXXXXXXXXXXXXXXXXXX
   ```
5. Restart the AppDaemon add-on.

See the [full README](https://github.com/agjendem/ha-spond-tracker#readme)
for configuration reference, event-bus payloads, troubleshooting, and
migration notes.

## Notifications without writing YAML

The repo ships [automation
blueprints](https://github.com/agjendem/ha-spond-tracker#automation-blueprints)
that turn the event-bus events into mobile notifications via point-and-
click setup. One blueprint per notification kind (new task / event
cancelled / event changed / task reminder), instantiate once per
tracked member.

## Localization

User-facing text (calendar SUMMARY/DESCRIPTION and sensor friendly_name)
ships with English (default) and Norwegian Bokmål (`nb`). Adding more
languages is just a new JSON file in `translations/` — PRs welcome.
