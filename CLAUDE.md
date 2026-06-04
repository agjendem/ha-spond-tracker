# Claude Code — Spond Tracker context

## Project

Native Home Assistant custom integration that polls Spond (sport/activity
scheduling service) and exposes per-member calendar entities, sensors, and
event bus events. Supports multiple Spond accounts with cross-account
deduplication.

- HACS custom integration, installed at `/config/custom_components/spond_tracker/`
- Test HA instance: `192.168.1.205` (SSH as `anders`, passwordless)
- GitHub: `agjendem/ha-spond-tracker` (public, MIT)

## Development workflow

```bash
ruff check . && ruff format --check .   # lint — same as CI
pytest                                   # 172 tests as of last count
```

Commits use **Conventional Commits** (`feat:`, `fix:`, `docs:`, etc.).
`release-please` auto-opens a release PR on each merge to `main`.
Never push directly to `main`; always go via PR with green CI.

See `CONTRIBUTING.md` for full conventions and release workflow.

## Architecture

| File | Role |
|------|------|
| `__init__.py` | `async_setup_entry`, `async_unload_entry`, v1→v2 migration |
| `coordinator.py` | `SpondDataUpdateCoordinator` — polls Spond, fires HA bus events, holds `CoordinatorData` |
| `sensor.py` | `SpondEventsSensor`, `SpondTasksSensor` — `CoordinatorEntity` subclasses |
| `calendar.py` | `SpondCalendarEntity` — `CoordinatorEntity` + `CalendarEntity` |
| `config_flow.py` | Config flow, options flow, reauth flow, reconfigure flow |
| `spond_helpers.py` | Pure functions: event dedup, fingerprinting, member matching |
| `spond_i18n.py` | `load_translations()` — loads `translations/*.json` from disk |
| `diagnostics.py` | `async_get_config_entry_diagnostics` — redacts passwords |
| `icons.json` | Entity icon definitions (Gold IQS `icon-translations`) |
| `brand/` | Local brand assets served by HA proxy API (HA 2026.3+) |

Key invariants:
- **`entry.runtime_data`** holds the coordinator — never use `hass.data[DOMAIN]`
- **`PARALLEL_UPDATES = 1`** in sensor.py and calendar.py
- **`async_config_entry_first_refresh()`** called in `async_setup_entry` — raises `ConfigEntryNotReady` on first-poll failure
- **`ConfigEntryAuthFailed`** raised by coordinator when all accounts return 401/403 → triggers reauth notification in HA UI
- Member names matched by **first token** (lowercased) — "Alice Smith" → canonical `"alice"`

## Integration Quality Scale

Current level: **Silver** (`quality_scale: silver` in `manifest.json`)

Rule docs base URL: `https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/<rule-name>/`

### Bronze — all 18 rules ✅

| Rule | Docs | Status | Notes |
|------|------|--------|-------|
| `action-setup` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/action-setup/) | ✅ N/A | No custom actions |
| `appropriate-polling` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/appropriate-polling/) | ✅ | `DataUpdateCoordinator`, configurable 5–1440 min |
| `brands` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/brands/) | ✅ | `brand/` with icon.png 256×256, icon@2x.png 512×512, dark variants, logo |
| `common-modules` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/common-modules/) | ✅ | coordinator.py, const.py, config_flow.py, spond_helpers.py |
| `config-flow` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/config-flow/) | ✅ | Full UI config flow |
| `config-flow-test-coverage` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/config-flow-test-coverage/) | ✅ | `tests/test_config_flow.py` — all steps + errors + options |
| `dependency-transparency` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/dependency-transparency/) | ✅ | `spond==1.2.1` pinned in manifest, on PyPI |
| `docs-actions` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-actions/) | ✅ N/A | No custom actions |
| `docs-high-level-description` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-high-level-description/) | ✅ | README intro + Features section |
| `docs-installation-instructions` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-installation-instructions/) | ✅ | HACS + manual steps in README |
| `docs-removal-instructions` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-removal-instructions/) | ✅ | "Removing the integration" section in README |
| `entity-event-setup` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/entity-event-setup/) | ✅ | `CoordinatorEntity` handles subscriptions in `async_added_to_hass` |
| `entity-unique-id` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/entity-unique-id/) | ✅ | `_attr_unique_id` on all entities |
| `has-entity-name` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/has-entity-name/) | ✅ | `_attr_has_entity_name = True` on all entities |
| `runtime-data` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/runtime-data/) | ✅ | `entry.runtime_data = coordinator` |
| `test-before-configure` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/test-before-configure/) | ✅ | `_validate_and_discover()` validates credentials in config flow |
| `test-before-setup` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/test-before-setup/) | ✅ | `async_config_entry_first_refresh()` in `async_setup_entry` |
| `unique-config-entry` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/unique-config-entry/) | ✅ | `already_configured` abort in config flow |

### Silver — all 10 rules ✅

| Rule | Docs | Status | Notes |
|------|------|--------|-------|
| `action-exceptions` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/action-exceptions/) | ✅ N/A | No custom actions |
| `config-entry-unloading` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/config-entry-unloading/) | ✅ | `async_unload_platforms` in `async_unload_entry` |
| `docs-configuration-parameters` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-configuration-parameters/) | ✅ | Options documented in README (poll interval, add/remove account) |
| `docs-installation-parameters` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-installation-parameters/) | ✅ | Setup parameters (username, member selection) documented in README |
| `entity-unavailable` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/entity-unavailable/) | ✅ | `CoordinatorEntity` marks entities unavailable on failed poll |
| `integration-owner` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/integration-owner/) | ✅ | `codeowners: ["@agjendem"]` in manifest |
| `log-when-unavailable` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/log-when-unavailable/) | ✅ | Coordinator logs WARNING on transition to unavailable, INFO on recovery |
| `parallel-updates` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/parallel-updates/) | ✅ | `PARALLEL_UPDATES = 1` in sensor.py and calendar.py |
| `reauthentication-flow` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/reauthentication-flow/) | ✅ | `async_step_reauth` + `async_step_reauth_confirm` in config_flow.py |
| `test-coverage` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/test-coverage/) | ✅ | 172 tests across config_flow, coordinator, sensor, calendar, helpers, i18n |

### Gold — all applicable rules ✅

| Rule | Docs | Status | Notes |
|------|------|--------|-------|
| `devices` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/devices/) | ✅ | `DeviceInfo` per tracked member (`entry_type=SERVICE`) |
| `diagnostics` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/diagnostics/) | ✅ | `diagnostics.py` with password redaction via `async_redact_data` |
| `discovery` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/discovery/) | ✅ N/A | Cloud service — no local discovery possible |
| `discovery-update-info` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/discovery-update-info/) | ✅ N/A | N/A |
| `docs-data-update` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-data-update/) | ✅ | "Data updates" section in README |
| `docs-examples` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-examples/) | ✅ | Example automation + 4 importable blueprints in README |
| `docs-known-limitations` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-known-limitations/) | ✅ | "Known limitations" section in README |
| `docs-supported-devices` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-supported-devices/) | ✅ N/A | Service, not device-based |
| `docs-supported-functions` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-supported-functions/) | ✅ | Calendars, sensors, event bus all documented in README |
| `docs-troubleshooting` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-troubleshooting/) | ✅ | Troubleshooting section in README |
| `docs-use-cases` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/docs-use-cases/) | ⚠️ | Blueprints + example automation cover this, but no explicit "Use cases" section |
| `dynamic-devices` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/dynamic-devices/) | ✅ N/A | N/A |
| `entity-category` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/entity-category/) | ✅ | Measurement sensors correctly have no `EntityCategory` |
| `entity-device-class` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/entity-device-class/) | ✅ N/A | No standard `SensorDeviceClass` fits event/task counts |
| `entity-disabled-by-default` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/entity-disabled-by-default/) | ✅ | All entities are useful by default |
| `entity-translations` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/entity-translations/) | ✅ | `_attr_translation_key` + `_attr_translation_placeholders` on sensors; keys under `entity.sensor` in strings.json |
| `exception-translations` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/exception-translations/) | ✅ | Error strings in strings.json + translations/*.json |
| `icon-translations` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/icon-translations/) | ✅ | `icons.json` maps sensor translation keys to mdi icons |
| `reconfiguration-flow` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/reconfiguration-flow/) | ✅ | `async_step_reconfigure` in config_flow.py |
| `repair-issues` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/repair-issues/) | ✅ | `async_create_issue` after 3 consecutive non-auth poll failures; auto-cleared on recovery |
| `stale-devices` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/stale-devices/) | ✅ N/A | N/A |

**Gold status**: all applicable rules met. Next target would be Platinum (blocked by upstream `spond` library).

### Platinum — not achievable ❌

| Rule | Docs | Status | Notes |
|------|------|--------|-------|
| `async-dependency` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/async-dependency/) | ⚠️ | `spond` uses aiohttp but creates its own `ClientSession` internally |
| `inject-websession` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/inject-websession/) | ❌ | `spond` v1.2.1 has no session injection point — requires upstream library change |
| `strict-typing` | [↗](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/strict-typing/) | ❌ | Not fully typed |

## Translation parity

All keys in `strings.json` must be present in **both**
`translations/en.json` and `translations/nb.json`. The CI `lint` workflow
validates this. When adding new strings:

1. Add to `strings.json`
2. Add English text to `translations/en.json`
3. Add Norwegian text to `translations/nb.json`

For new entity names: add under `entity.sensor.<key>.name` (not the old `sensors` key).
For new entity icons: add the matching key in `icons.json`.

## Brand assets

Stored in `custom_components/spond_tracker/brand/` — served by HA's local
brands proxy API (since HA 2026.3.0; no PR to `home-assistant/brands` needed).
See: <https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api/>

| File | Size | Source |
|------|------|--------|
| `icon.png` | 256×256 | Spond safari-pinned-tab.svg, transparent bg, opacity 1.0 |
| `icon@2x.png` | 512×512 | Same, 2× |
| `dark_icon.png` | 256×256 | Same SVG with original dark red background (#1A0100) |
| `dark_icon@2x.png` | 512×512 | Same, 2× |
| `logo.png` | 796×224 | Spond wordmark PNG (orange-red on transparent) |
| `logo@2x.png` | 1593×448 | Same, 2× |

Source SVG: `https://media.spond.com/uploads/favicons/safari-pinned-tab.svg`
Source logo: `https://www.spond.com/app/themes/sozo/public/images/logo.png`

Regeneration requires `brew install cairo` + `pip install cairosvg pillow` +
`DYLD_LIBRARY_PATH=/opt/homebrew/lib python3 <script>`. Size requirements:
icon.png must be 256×256, icon@2x.png 512×512.
