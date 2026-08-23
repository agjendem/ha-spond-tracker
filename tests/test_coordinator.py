"""Smoke tests for SpondDataUpdateCoordinator."""

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spond_tracker.const import (
    CONF_ACCOUNTS,
    CONF_EVENT_WINDOW_DAYS,
    CONF_INCLUDE_UNINVITED,
    CONF_MEMBERS,
    CONF_NIGHT_END,
    CONF_NIGHT_POLL_INTERVAL,
    CONF_NIGHT_START,
    CONF_PASSWORD,
    CONF_UNINVITED_HORIZON_DAYS,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.spond_tracker.coordinator import (
    MAX_EVENTS,
    CoordinatorData,
    SpondDataUpdateCoordinator,
)

MOCK_MEMBERS = [{"canonical": "alice", "display_name": "Alice Smith"}]
MOCK_ACCOUNTS = [{CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"}]

NOW = datetime.now(UTC)
TOMORROW = NOW + timedelta(days=1)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _make_entry(hass, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNTS: MOCK_ACCOUNTS, CONF_MEMBERS: MOCK_MEMBERS},
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


def _mock_spond_instance(events=None, error=None):
    instance = MagicMock()
    if error:
        instance.get_events = AsyncMock(side_effect=error)
    else:
        instance.get_events = AsyncMock(return_value=events or [])
    instance.clientsession = AsyncMock()
    return instance


async def _do_refresh(coord):
    with patch.object(coord, "_load_strings", new=AsyncMock()):
        await coord.async_refresh()


# ── happy path ────────────────────────────────────────────────────────────────


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_poll_returns_coordinator_data(mock_spond_cls, hass):
    mock_spond_cls.return_value = _mock_spond_instance()
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    await _do_refresh(coord)
    assert isinstance(coord.data, CoordinatorData)
    assert coord.last_update_success is True


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_poll_populates_members_dict(mock_spond_cls, hass):
    mock_spond_cls.return_value = _mock_spond_instance()
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    await _do_refresh(coord)
    assert "alice" in coord.data.events
    assert "alice" in coord.data.tasks


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_poll_records_timestamp(mock_spond_cls, hass):
    mock_spond_cls.return_value = _mock_spond_instance()
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    before = datetime.now(UTC)
    await _do_refresh(coord)
    assert coord.data.polled_at >= before


# ── authentication failure ────────────────────────────────────────────────────


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_auth_failure_raises_config_entry_auth_failed(mock_spond_cls, hass):
    mock_spond_cls.return_value = _mock_spond_instance(error=Exception("401 unauthorized"))
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    coord.strings = {}
    with (
        pytest.raises(ConfigEntryAuthFailed),
        patch.object(coord, "_load_strings", new=AsyncMock()),
    ):
        await coord._async_update_data()


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_forbidden_also_raises_config_entry_auth_failed(mock_spond_cls, hass):
    mock_spond_cls.return_value = _mock_spond_instance(error=Exception("403 forbidden"))
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    coord.strings = {}
    with (
        pytest.raises(ConfigEntryAuthFailed),
        patch.object(coord, "_load_strings", new=AsyncMock()),
    ):
        await coord._async_update_data()


# ── connection failure ────────────────────────────────────────────────────────


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_connection_error_sets_unavailable(mock_spond_cls, hass):
    mock_spond_cls.return_value = _mock_spond_instance(error=Exception("connection timeout"))
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    await _do_refresh(coord)
    assert coord.last_update_success is False


# ── log-when-unavailable ─────────────────────────────────────────────────────


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_warns_once_on_first_unavailable(mock_spond_cls, hass, caplog):
    mock_spond_cls.return_value = _mock_spond_instance(error=Exception("connection timeout"))
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    with caplog.at_level(logging.WARNING, logger="custom_components.spond_tracker.coordinator"):
        await _do_refresh(coord)
    assert any("unavailable" in r.message for r in caplog.records if r.levelno == logging.WARNING)


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_logs_recovery_after_unavailable(mock_spond_cls, hass, caplog):
    # First poll fails
    mock_spond_cls.return_value = _mock_spond_instance(error=Exception("connection timeout"))
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    await _do_refresh(coord)
    assert coord.last_update_success is False

    # Second poll succeeds → should log recovery at INFO
    mock_spond_cls.return_value = _mock_spond_instance()
    with caplog.at_level(logging.INFO, logger="custom_components.spond_tracker.coordinator"):
        await _do_refresh(coord)
    assert any("available again" in r.message for r in caplog.records if r.levelno == logging.INFO)
    assert coord.last_update_success is True


# ── uninvited events ─────────────────────────────────────────────────────────


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_uninvited_events_are_not_requested_by_default(mock_spond_cls, hass):
    """The Spond library filters them out unless asked, and that stays the default."""
    instance = _mock_spond_instance()
    mock_spond_cls.return_value = instance
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    await _do_refresh(coord)
    assert instance.get_events.await_args.kwargs["include_scheduled"] is False


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_option_switches_uninvited_events_on(mock_spond_cls, hass):
    instance = _mock_spond_instance()
    mock_spond_cls.return_value = instance
    entry = _make_entry(hass, options={CONF_INCLUDE_UNINVITED: True})
    coord = SpondDataUpdateCoordinator(hass, entry)
    await _do_refresh(coord)
    assert instance.get_events.await_args.kwargs["include_scheduled"] is True


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_event_ceiling_leaves_room_for_uninvited_events(mock_spond_cls, hass):
    """One account already returns ~170 events over 60 days with them included."""
    instance = _mock_spond_instance()
    mock_spond_cls.return_value = instance
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    await _do_refresh(coord)
    assert instance.get_events.await_args.kwargs["max_events"] >= 400


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_hitting_the_ceiling_is_logged(mock_spond_cls, hass, caplog):
    """Silent truncation is exactly how the missing events went unnoticed."""
    instance = _mock_spond_instance(events=[{"id": f"e{i}"} for i in range(MAX_EVENTS)])
    mock_spond_cls.return_value = instance
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    with caplog.at_level(logging.WARNING):
        await _do_refresh(coord)
    assert "ceiling" in caplog.text


# ── split fetch: confirmed window vs uninvited horizon ───────────────────────


def _window_days(call) -> int:
    """Days between min_end and max_end of one get_events call."""
    kw = call.kwargs
    return round((kw["max_end"] - kw["min_end"]).total_seconds() / 86400)


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_option_off_makes_a_single_request(mock_spond_cls, hass):
    """With uninvited events off nothing about the request should change."""
    instance = _mock_spond_instance()
    mock_spond_cls.return_value = instance
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    await _do_refresh(coord)
    assert instance.get_events.await_count == 1
    call = instance.get_events.await_args_list[0]
    assert call.kwargs["include_scheduled"] is False
    assert _window_days(call) == 60


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_option_on_splits_into_two_requests(mock_spond_cls, hass):
    """Confirmed events keep the full window; only uninvited ones are cut short."""
    instance = _mock_spond_instance()
    mock_spond_cls.return_value = instance
    entry = _make_entry(hass, options={CONF_INCLUDE_UNINVITED: True})
    coord = SpondDataUpdateCoordinator(hass, entry)
    await _do_refresh(coord)
    assert instance.get_events.await_count == 2
    confirmed, uninvited = instance.get_events.await_args_list
    assert confirmed.kwargs["include_scheduled"] is False
    assert _window_days(confirmed) == 60
    assert uninvited.kwargs["include_scheduled"] is True
    assert _window_days(uninvited) == 14


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_both_windows_are_configurable(mock_spond_cls, hass):
    instance = _mock_spond_instance()
    mock_spond_cls.return_value = instance
    entry = _make_entry(
        hass,
        options={
            CONF_INCLUDE_UNINVITED: True,
            CONF_EVENT_WINDOW_DAYS: 90,
            CONF_UNINVITED_HORIZON_DAYS: 21,
        },
    )
    coord = SpondDataUpdateCoordinator(hass, entry)
    await _do_refresh(coord)
    confirmed, uninvited = instance.get_events.await_args_list
    assert _window_days(confirmed) == 90
    assert _window_days(uninvited) == 21


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_uninvited_horizon_is_clamped_to_the_window(mock_spond_cls, hass):
    """Provisional events on dates with no confirmed events would make no sense."""
    instance = _mock_spond_instance()
    mock_spond_cls.return_value = instance
    entry = _make_entry(
        hass,
        options={
            CONF_INCLUDE_UNINVITED: True,
            CONF_EVENT_WINDOW_DAYS: 7,
            CONF_UNINVITED_HORIZON_DAYS: 30,
        },
    )
    coord = SpondDataUpdateCoordinator(hass, entry)
    await _do_refresh(coord)
    confirmed, uninvited = instance.get_events.await_args_list
    assert _window_days(confirmed) == 7
    assert _window_days(uninvited) == 7


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_event_present_in_both_fetches_is_not_duplicated(mock_spond_cls, hass):
    """The two windows overlap by design, so the same event arrives twice."""
    event = {
        "id": "e1",
        "heading": "Practice",
        "startTimestamp": NOW.isoformat().replace("+00:00", "Z"),
        "endTimestamp": TOMORROW.isoformat().replace("+00:00", "Z"),
        "cancelled": False,
        "behalfOfIds": ["m1"],
        "recipients": {"group": {"members": [{"id": "m1", "firstName": "Alice"}]}},
        "responses": {"acceptedIds": ["m1"]},
        "tasks": {},
    }
    instance = _mock_spond_instance(events=[event])
    mock_spond_cls.return_value = instance
    entry = _make_entry(hass, options={CONF_INCLUDE_UNINVITED: True})
    coord = SpondDataUpdateCoordinator(hass, entry)
    await _do_refresh(coord)
    assert instance.get_events.await_count == 2
    assert len(coord.data.events["alice"]) == 1


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
async def test_ceiling_warning_names_the_fetch_that_hit_it(mock_spond_cls, hass, caplog):
    """Both requests have their own ceiling, so the log has to say which one."""
    instance = _mock_spond_instance(events=[{"id": f"e{i}"} for i in range(MAX_EVENTS)])
    mock_spond_cls.return_value = instance
    entry = _make_entry(hass, options={CONF_INCLUDE_UNINVITED: True})
    coord = SpondDataUpdateCoordinator(hass, entry)
    with caplog.at_level(logging.WARNING):
        await _do_refresh(coord)
    assert "confirmed fetch" in caplog.text
    assert "uninvited fetch" in caplog.text


# ── day/night polling ────────────────────────────────────────────────────────


# Quiet hours are evaluated in the instance's local time, and the test harness
# defaults to US/Pacific — so every test here pins the zone explicitly.
NIGHT_OPTIONS = {
    CONF_NIGHT_POLL_INTERVAL: 180,
    CONF_NIGHT_START: "23:00:00",
    CONF_NIGHT_END: "06:00:00",
}


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
@pytest.mark.freeze_time("2026-06-15 12:00:00+02:00")
async def test_daytime_keeps_the_normal_interval(mock_spond_cls, hass):
    await hass.config.async_set_time_zone("Europe/Oslo")
    mock_spond_cls.return_value = _mock_spond_instance()
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass, options=NIGHT_OPTIONS))
    await _do_refresh(coord)
    assert coord.update_interval == timedelta(minutes=30)


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
@pytest.mark.freeze_time("2026-06-15 01:00:00+02:00")
async def test_night_stretches_the_interval(mock_spond_cls, hass):
    await hass.config.async_set_time_zone("Europe/Oslo")
    mock_spond_cls.return_value = _mock_spond_instance()
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass, options=NIGHT_OPTIONS))
    await _do_refresh(coord)
    assert coord.update_interval == timedelta(minutes=180)


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
@pytest.mark.freeze_time("2026-06-15 04:30:00+02:00")
async def test_last_night_poll_lands_when_the_window_closes(mock_spond_cls, hass):
    """90 minutes to 06:00, not a full 180 that would overshoot to 07:30."""
    await hass.config.async_set_time_zone("Europe/Oslo")
    mock_spond_cls.return_value = _mock_spond_instance()
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass, options=NIGHT_OPTIONS))
    await _do_refresh(coord)
    assert coord.update_interval == timedelta(minutes=90)


@patch("custom_components.spond_tracker.coordinator.spond_lib.Spond")
@pytest.mark.freeze_time("2026-06-15 03:00:00+02:00")
async def test_night_polling_is_off_by_default(mock_spond_cls, hass):
    """Existing installs must keep polling exactly as they did."""
    await hass.config.async_set_time_zone("Europe/Oslo")
    mock_spond_cls.return_value = _mock_spond_instance()
    coord = SpondDataUpdateCoordinator(hass, _make_entry(hass))
    await _do_refresh(coord)
    assert coord.update_interval == timedelta(minutes=30)
