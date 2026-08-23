"""Constants for the Spond Tracker integration."""

from homeassistant.const import Platform

DOMAIN = "spond_tracker"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_ACCOUNTS = "accounts"
CONF_MEMBERS = "members"
CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_POLL_INTERVAL = 30  # minutes

# Measured on live data: 96% of invitations go out between 09:00 and 21:00, and
# no event starts between 22:00 and 08:00. Polling through the small hours costs
# bandwidth and buys nothing, so the interval can be relaxed overnight.
CONF_NIGHT_POLL_INTERVAL = "night_poll_interval"
DEFAULT_NIGHT_POLL_INTERVAL = 0  # 0 = poll at the same rate around the clock
CONF_NIGHT_START = "night_start"
CONF_NIGHT_END = "night_end"
DEFAULT_NIGHT_START = "23:00:00"
DEFAULT_NIGHT_END = "06:00:00"

# Spond hides events whose invitation has not been sent yet unless they are
# explicitly asked for, so most of a season is invisible by default. Fetching
# them multiplies the payload roughly sevenfold, which is why the Spond library
# leaves them out and why this is opt-in.
CONF_INCLUDE_UNINVITED = "include_uninvited"
DEFAULT_INCLUDE_UNINVITED = False

# Spond embeds the full recipient list — every player plus their guardians — in
# each event, so one event weighs about 24 KB. How far ahead to look is
# therefore the single biggest lever on how much gets downloaded, which is why
# both horizons are settings rather than constants.
CONF_EVENT_WINDOW_DAYS = "event_window_days"
DEFAULT_EVENT_WINDOW_DAYS = 60

# Uninvited events are what make the payload large, and they are the least
# interesting far ahead: nothing can be answered and the plans still change.
CONF_UNINVITED_HORIZON_DAYS = "uninvited_horizon_days"
DEFAULT_UNINVITED_HORIZON_DAYS = 14

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
