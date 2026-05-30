"""Pytest config — exposes apps/spond_tracker/ as an importable path.

AppDaemon runs each app from its own directory, with that directory on
sys.path. We mimic that for tests so sibling modules import naturally
(`import spond_helpers`, not `from apps.spond_tracker import ...`).
"""

import sys
from pathlib import Path

APP_DIR = Path(__file__).parent.parent / "apps" / "spond_tracker"
sys.path.insert(0, str(APP_DIR))
