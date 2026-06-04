"""Pytest config for Spond Tracker tests."""

import sys
from pathlib import Path

pytest_plugins = ["pytest_homeassistant_custom_component"]

INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / "spond_tracker"
sys.path.insert(0, str(INTEGRATION_DIR))
