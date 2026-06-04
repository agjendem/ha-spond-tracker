"""Pytest config — exposes importable paths for both the AppDaemon app and
the native integration helpers.

The AppDaemon app dir is added so existing tests (`import spond_helpers`,
`from spond_i18n import ...`) continue to resolve against the original
apps/spond_tracker/ copy without change.
"""

import sys
from pathlib import Path

APP_DIR = Path(__file__).parent.parent / "apps" / "spond_tracker"
INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / "spond_tracker"
sys.path.insert(0, str(INTEGRATION_DIR))
sys.path.insert(0, str(APP_DIR))  # APP_DIR first: existing tests import from apps/
