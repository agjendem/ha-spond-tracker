"""Constants for the Spond Tracker integration."""

from homeassistant.const import Platform

DOMAIN = "spond_tracker"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_ACCOUNTS = "accounts"
CONF_MEMBERS = "members"
CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_POLL_INTERVAL = 30  # minutes

PLATFORMS = [Platform.CALENDAR, Platform.SENSOR]

# --- Actions ---
SERVICE_RESPOND_TO_TASK = "respond_to_task"
SERVICE_SNOOZE_TASK = "snooze_task"

ATTR_TASK = "task"
ATTR_RESPONSE = "response"
ATTR_UNTIL = "until"
ATTR_DURATION = "duration"

RESPONSE_ACCEPT = "accept"
RESPONSE_DECLINE = "decline"

# Snoozing is a Home Assistant concept: Spond only knows accepted, declined and
# unanswered, so "ask me later" has to be remembered on this side.
SNOOZE_STORAGE_KEY = f"{DOMAIN}.snooze"
SNOOZE_STORAGE_VERSION = 1
DEFAULT_SNOOZE_HOURS = 24
