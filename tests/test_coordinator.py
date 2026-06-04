"""Smoke tests for SpondDataUpdateCoordinator."""

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spond_tracker.const import (
    CONF_ACCOUNTS,
    CONF_MEMBERS,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.spond_tracker.coordinator import CoordinatorData, SpondDataUpdateCoordinator

MOCK_MEMBERS = [{"canonical": "alice", "display_name": "Alice Smith"}]
MOCK_ACCOUNTS = [{CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"}]

NOW = datetime.now(UTC)
TOMORROW = NOW + timedelta(days=1)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _make_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCOUNTS: MOCK_ACCOUNTS, CONF_MEMBERS: MOCK_MEMBERS},
        options={},
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
