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
