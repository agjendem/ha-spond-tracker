"""Localization for Spond Tracker.

Loads translation JSON files from `translations/` next to this module.
The `calendar.*` and `sensors.*` keys are used at runtime by entity code.
The HA config-flow UI uses the `config.*` and `options.*` keys via HA's
own translation loading — both sets live in the same JSON file.
"""

import json
from pathlib import Path

TRANSLATIONS_DIR = Path(__file__).parent / "translations"

STATUS_EMOJI = {
    "accepted": "✅",
    "declined": "❌",
    "unanswered": "❓",
    "waitinglist": "⏳",
    "unknown": "❔",
    "cancelled": "🚫",
}

TASK_MARKER = "📋"


def load_translations(strings_dir: Path, lang: str) -> tuple[dict, str]:
    """Load the translations JSON for `lang` with fallback chain: lang → base → en."""
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
