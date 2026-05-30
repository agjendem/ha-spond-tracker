"""Tests for spond_i18n."""

import json
from pathlib import Path

import pytest
from spond_i18n import STATUS_EMOJI, TRANSLATIONS_DIR, load_translations


class TestLoadTranslations:
    def test_default_en(self) -> None:
        data, resolved = load_translations(TRANSLATIONS_DIR, "en")
        assert resolved == "en"
        assert "calendar" in data
        assert "sensors" in data

    def test_nb(self) -> None:
        data, resolved = load_translations(TRANSLATIONS_DIR, "nb")
        assert resolved == "nb"
        # Norwegian-specific value
        assert data["calendar"]["cancelled_prefix"] == "AVLYST: "

    def test_no_alias_maps_to_nb(self) -> None:
        data, resolved = load_translations(TRANSLATIONS_DIR, "no")
        # The legacy code "no" is normalized to "nb" before lookup
        assert resolved == "nb"
        assert data["calendar"]["cancelled_prefix"] == "AVLYST: "

    def test_region_strip_fallback(self) -> None:
        # "en-US" doesn't exist -> falls back to "en" (base)
        data, resolved = load_translations(TRANSLATIONS_DIR, "en-US")
        assert resolved == "en"
        assert "calendar" in data

    def test_unknown_falls_back_to_en(self) -> None:
        data, resolved = load_translations(TRANSLATIONS_DIR, "xx")
        assert resolved == "en"
        assert "calendar" in data

    def test_unknown_with_region_falls_back_to_en(self) -> None:
        # "xx-YY" -> neither "xx-YY" nor "xx" exists -> en
        _data, resolved = load_translations(TRANSLATIONS_DIR, "xx-YY")
        assert resolved == "en"

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        data, resolved = load_translations(tmp_path, "en")
        assert data == {}
        assert resolved == "en"


class TestStatusEmoji:
    @pytest.mark.parametrize(
        "status",
        ["accepted", "declined", "unanswered", "waitinglist", "unknown", "cancelled"],
    )
    def test_every_known_status_has_emoji(self, status: str) -> None:
        assert status in STATUS_EMOJI
        assert len(STATUS_EMOJI[status]) >= 1


class TestTranslationParity:
    """Every shipped translation must have the same key shape as en.json.

    This is also enforced in CI by lint.yml (the `translations` job), but
    asserting it as a unit test catches it earlier in local dev.
    """

    @staticmethod
    def _flatten(d: dict, prefix: str = "") -> set[str]:
        keys: set[str] = set()
        for k, v in d.items():
            full = f"{prefix}{k}"
            if isinstance(v, dict):
                keys |= TestTranslationParity._flatten(v, full + ".")
            else:
                keys.add(full)
        return keys

    @pytest.mark.parametrize(
        "lang_file",
        sorted(p.name for p in TRANSLATIONS_DIR.glob("*.json") if p.name != "en.json"),
    )
    def test_keys_match_en(self, lang_file: str) -> None:
        en = json.loads((TRANSLATIONS_DIR / "en.json").read_text())
        other = json.loads((TRANSLATIONS_DIR / lang_file).read_text())
        en_keys = self._flatten(en)
        other_keys = self._flatten(other)
        assert en_keys == other_keys, (
            f"{lang_file}: missing={sorted(en_keys - other_keys)} "
            f"extra={sorted(other_keys - en_keys)}"
        )
