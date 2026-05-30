"""Localization for spond_tracker.

Loads translation JSON files from `translations/` next to this module.
Exposes `load_translations()` which performs the fallback-chain lookup
and `STATUS_EMOJI` for response-status icons (these are universal
symbols, not language-specific).
"""

import json
from pathlib import Path

TRANSLATIONS_DIR = Path(__file__).parent / "translations"

# Universal status icons used in calendar SUMMARY across all languages.
STATUS_EMOJI = {
    "accepted": "✓",
    "declined": "✗",
    "unanswered": "?",
    "waitinglist": "…",
    "unknown": "·",
    "cancelled": "🚫",
}


def load_translations(strings_dir: Path, lang: str) -> tuple[dict, str]:
    """Load the translations JSON file for `lang`.

    Returns (data, resolved_lang). Falls back through:
      lang -> language-base (strip region) -> en.
    The legacy code "no" is mapped to "nb" (Bokmål) for BCP-47 compliance.
    """
    if lang == "no":
        lang = "nb"
    chain: list[str] = [lang]
    if "-" in lang:
        chain.append(lang.split("-", 1)[0])
    if "en" not in chain:
        chain.append("en")
    for code in chain:
        path = strings_dir / f"{code}.json"
        if path.exists():
            return json.loads(path.read_text()), code
    return {}, "en"
