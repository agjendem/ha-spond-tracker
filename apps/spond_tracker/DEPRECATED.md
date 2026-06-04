# Deprecated: AppDaemon app

The AppDaemon version of Spond Tracker is superseded by the native Home
Assistant custom integration in `custom_components/spond_tracker/`.

## Why migrate?

- No AppDaemon add-on required
- Setup via UI config flow (no YAML editing)
- Calendar entities created automatically (no manual `local_calendar` setup)
- Listed under HACS → Integrations

## Migration steps

1. Add via **Settings → Devices & Services → Add Integration → Spond Tracker**
2. Enter the same credentials as in your `apps.yaml`
3. Select the same members — calendars and sensors are created automatically
4. Update any dashboards or automations that reference the old entity IDs:
   - `sensor.spond_<name>` → `sensor.spond_tracker_<name>_events_today`
   - `sensor.spond_<name>_tasks` → `sensor.spond_tracker_<name>_tasks`
5. Comment out or remove the `spond_tracker:` block in `apps.yaml` and restart AppDaemon
6. Delete the `local_calendar` config entries that AppDaemon was writing to

**Automation blueprints** (`blueprints/`) work without changes — the event
bus event types and their data fields are identical.
