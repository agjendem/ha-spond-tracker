"""Pytest config — exposes the native integration helpers as importable modules."""

import sys
from pathlib import Path

INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / "spond_tracker"
sys.path.insert(0, str(INTEGRATION_DIR))
