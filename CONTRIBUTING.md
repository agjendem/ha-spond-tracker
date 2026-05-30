# Contributing

Thanks for taking an interest. This document covers the conventions used
in this repo so contributions land cleanly.

## Commit messages

Commits on `main` follow the
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
spec. The release automation (`release-please`) parses commit messages
to decide the next semver bump and to generate `CHANGELOG.md` entries.

| Prefix          | Meaning                            | Version bump (pre-1.0) |
| --------------- | ---------------------------------- | ---------------------- |
| `feat:`         | New user-visible feature           | minor (0.1.0 → 0.2.0)  |
| `fix:`          | Bug fix                            | patch (0.1.0 → 0.1.1)  |
| `perf:`         | Performance improvement            | patch                  |
| `deps:`         | Dependency bump                    | patch                  |
| `docs:`         | Documentation only                 | no bump                |
| `refactor:`     | Code change without behavior diff  | no bump                |
| `test:`         | Test changes only                  | no bump                |
| `build:`        | Build / packaging                  | no bump                |
| `ci:`           | CI config changes                  | no bump                |
| `chore:`        | Other maintenance                  | no bump                |
| `feat!:` / `BREAKING CHANGE:` footer | Breaking change | minor (pre-1.0) / major (post-1.0) |

Examples:

```
feat: add configurable timezone via apps.yaml

fix(ics): preserve historic events with timezone-naive DTSTART

docs(readme): clarify how to find config_entry_id

refactor!: rename sensor.spond_<name>_oppgaver to _tasks

BREAKING CHANGE: dashboards, automations, and templates referencing
the old entity_id must be updated.
```

The body and footer are free-form; only the prefix (and the optional `!`
or `BREAKING CHANGE:` marker) drive automation.

## Release workflow

1. Land work on `main` with conventional-commit messages.
2. `release-please` opens (or updates) a PR titled
   `chore(main): release X.Y.Z` containing the next version bump and a
   generated `CHANGELOG.md` entry. The PR auto-updates on each push.
3. Review + merge that PR. On merge, `release-please` tags the release
   and creates the corresponding GitHub Release.
4. HACS detects the new tag within ~1 hour and offers it to users.

There is no manual `gh release create` step.

## Local checks

Before pushing, run the same commands CI runs:

```bash
ruff check .
ruff format --check .
python -m json.tool apps/spond_tracker/translations/en.json > /dev/null
python -m json.tool apps/spond_tracker/translations/nb.json > /dev/null
python -m py_compile apps/spond_tracker/spond_tracker.py
```

See [README.md → Development](./README.md#development) for venv setup.

## Adding a translation

1. Copy `apps/spond_tracker/translations/en.json` to a new file named
   after the BCP-47 language code (e.g. `da.json`, `de.json`, `sv.json`).
2. Translate every value. Keys must match `en.json` exactly — the
   `lint` workflow fails if any keys are missing or extra.
3. Open a PR with the prefix `feat(i18n): add <language> translation`.
