"""Tests for the native HA integration's translation files and i18n helpers.

Uses importlib to load the native spond_i18n.py directly, so this is
independent of the AppDaemon version loaded by conftest via sys.path.
"""

import importlib.util
import json
from pathlib import Path
from typing import ClassVar

import pytest

# ── load native i18n module ───────────────────────────────────────────────────
_NATIVE_DIR = Path(__file__).parent.parent / "custom_components" / "spond_tracker"
_spec = importlib.util.spec_from_file_location("native_spond_i18n", _NATIVE_DIR / "spond_i18n.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

NATIVE_TRANSLATIONS_DIR: Path = _mod.TRANSLATIONS_DIR
native_load_translations = _mod.load_translations
NATIVE_STATUS_EMOJI: dict = _mod.STATUS_EMOJI
NATIVE_TASK_MARKER: str = _mod.TASK_MARKER

_KNOWN_STATUSES = ["accepted", "declined", "waitinglist", "unanswered", "unknown", "cancelled"]


def _flatten(d: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for k, v in d.items():
        full = f"{prefix}{k}"
        if isinstance(v, dict):
            keys |= _flatten(v, full + ".")
        else:
            keys.add(full)
    return keys


def _load_json(lang: str) -> dict:
    path = NATIVE_TRANSLATIONS_DIR / f"{lang}.json"
    return json.loads(path.read_text())


# ── TestNativeLoadTranslations ────────────────────────────────────────────────


class TestNativeLoadTranslations:
    def test_en_loads(self) -> None:
        data, resolved = native_load_translations(NATIVE_TRANSLATIONS_DIR, "en")
        assert resolved == "en"
        assert "calendar" in data
        assert "sensors" in data

    def test_nb_loads(self) -> None:
        data, resolved = native_load_translations(NATIVE_TRANSLATIONS_DIR, "nb")
        assert resolved == "nb"
        assert data["calendar"]["cancelled_prefix"] == "AVLYST: "

    def test_no_maps_to_nb(self) -> None:
        _data, resolved = native_load_translations(NATIVE_TRANSLATIONS_DIR, "no")
        assert resolved == "nb"

    def test_en_us_falls_back_to_en(self) -> None:
        data, resolved = native_load_translations(NATIVE_TRANSLATIONS_DIR, "en-US")
        assert resolved == "en"
        assert "calendar" in data

    def test_unknown_falls_back_to_en(self) -> None:
        _data, resolved = native_load_translations(NATIVE_TRANSLATIONS_DIR, "xx")
        assert resolved == "en"

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        data, resolved = native_load_translations(tmp_path, "en")
        assert data == {}
        assert resolved == "en"


# ── TestNativeTranslationParity ───────────────────────────────────────────────


class TestNativeTranslationParity:
    """Every shipped translation file must have exactly the same key shape as en.json."""

    @pytest.mark.parametrize(
        "lang_file",
        sorted(p.name for p in NATIVE_TRANSLATIONS_DIR.glob("*.json") if p.name != "en.json"),
    )
    def test_keys_match_en(self, lang_file: str) -> None:
        en_keys = _flatten(_load_json("en"))
        other = json.loads((NATIVE_TRANSLATIONS_DIR / lang_file).read_text())
        other_keys = _flatten(other)
        assert en_keys == other_keys, (
            f"{lang_file}: missing={sorted(en_keys - other_keys)} "
            f"extra={sorted(other_keys - en_keys)}"
        )


# ── TestNativeCalendarKeys ────────────────────────────────────────────────────


class TestNativeCalendarKeys:
    """All runtime calendar string keys must be present in every translation."""

    _REQUIRED: ClassVar[list[str]] = [
        "cancelled_prefix",
        "status_label",
        "location_label",
        "address_label",
        "my_tasks_header",
        "all_tasks_header",
        "signed_up_suffix",
        "open_slot",
        "adults_only",
        "co_assignees_with",
        "task_for",
        "on_event",
        "task_signed_up",
        "task_with",
        "main_event_cancelled",
    ]

    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_calendar_keys_present(self, lang: str) -> None:
        data = _load_json(lang)
        cal = data.get("calendar", {})
        missing = [k for k in self._REQUIRED if k not in cal]
        assert missing == [], f"{lang}: missing calendar keys: {missing}"

    @pytest.mark.parametrize("status", _KNOWN_STATUSES)
    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_status_key_present(self, lang: str, status: str) -> None:
        data = _load_json(lang)
        cal = data.get("calendar", {})
        key = f"status_{status}"
        assert key in cal, f"{lang}: missing calendar.{key}"

    @pytest.mark.parametrize("status", _KNOWN_STATUSES)
    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_status_value_non_empty(self, lang: str, status: str) -> None:
        data = _load_json(lang)
        val = data["calendar"][f"status_{status}"]
        assert val and val.strip(), f"{lang}: calendar.status_{status} is blank"


# ── TestNativeSensorKeys ──────────────────────────────────────────────────────


class TestNativeSensorKeys:
    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_sensor_keys_present(self, lang: str) -> None:
        data = _load_json(lang)
        sensors = data.get("sensors", {})
        assert "events_friendly" in sensors, f"{lang}: missing sensors.events_friendly"
        assert "tasks_friendly" in sensors, f"{lang}: missing sensors.tasks_friendly"

    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_sensor_templates_contain_name_placeholder(self, lang: str) -> None:
        data = _load_json(lang)
        sensors = data["sensors"]
        assert "{name}" in sensors["events_friendly"]
        assert "{name}" in sensors["tasks_friendly"]


# ── TestNativeConfigFlowKeys ──────────────────────────────────────────────────


class TestNativeConfigFlowKeys:
    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_config_user_step(self, lang: str) -> None:
        data = _load_json(lang)
        step = data["config"]["step"]["user"]
        assert "title" in step
        assert "username" in step["data"]
        assert "password" in step["data"]

    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_config_members_step(self, lang: str) -> None:
        data = _load_json(lang)
        step = data["config"]["step"]["members"]
        assert "title" in step
        assert "members" in step["data"]

    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_config_errors(self, lang: str) -> None:
        data = _load_json(lang)
        errors = data["config"]["error"]
        assert "invalid_auth" in errors
        assert "cannot_connect" in errors

    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_config_abort_already_configured(self, lang: str) -> None:
        data = _load_json(lang)
        assert "already_configured" in data["config"]["abort"]


# ── TestNativeOptionsFlowKeys ─────────────────────────────────────────────────


class TestNativeOptionsFlowKeys:
    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_init_step(self, lang: str) -> None:
        data = _load_json(lang)
        step = data["options"]["step"]["init"]
        assert "title" in step
        assert "poll_interval" in step["data"]
        assert "{accounts}" in step["description"]

    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_add_account_step(self, lang: str) -> None:
        data = _load_json(lang)
        step = data["options"]["step"]["add_account"]
        assert "title" in step
        assert "username" in step["data"]
        assert "password" in step["data"]

    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_add_account_members_step(self, lang: str) -> None:
        data = _load_json(lang)
        step = data["options"]["step"]["add_account_members"]
        assert "title" in step
        assert "members" in step["data"]

    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_remove_account_step(self, lang: str) -> None:
        data = _load_json(lang)
        step = data["options"]["step"]["remove_account"]
        assert "title" in step
        assert "account" in step["data"]

    @pytest.mark.parametrize("lang", ["en", "nb"])
    def test_selector_action_options(self, lang: str) -> None:
        data = _load_json(lang)
        options = data["selector"]["action"]["options"]
        assert "add" in options
        assert "remove" in options
        assert options["add"].strip()
        assert options["remove"].strip()


# ── TestNativeStatusEmojiAndMarker ────────────────────────────────────────────


class TestNativeStatusEmojiAndMarker:
    @pytest.mark.parametrize("status", _KNOWN_STATUSES)
    def test_every_status_has_emoji(self, status: str) -> None:
        assert status in NATIVE_STATUS_EMOJI
        assert len(NATIVE_STATUS_EMOJI[status]) >= 1

    def test_task_marker_non_empty(self) -> None:
        assert NATIVE_TASK_MARKER and len(NATIVE_TASK_MARKER) >= 1

    def test_status_emoji_count_matches_known_statuses(self) -> None:
        # Guard against accidentally adding a status in one place and not the other
        assert set(NATIVE_STATUS_EMOJI.keys()) == set(_KNOWN_STATUSES)
