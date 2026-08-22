"""Tests for responding to and snoozing Spond tasks."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spond_tracker.const import (
    CONF_ACCOUNTS,
    CONF_MEMBERS,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.spond_tracker.coordinator import (
    CoordinatorData,
    SpondDataUpdateCoordinator,
)
from custom_components.spond_tracker.sensor import _is_outstanding

ACCOUNT = "user@example.com"
ENTRY_DATA = {
    CONF_ACCOUNTS: [{CONF_USERNAME: ACCOUNT, CONF_PASSWORD: "secret"}],
    CONF_MEMBERS: [{"canonical": "alice", "display_name": "Alice Smith"}],
}


def _task(uid="ev1::Drive", **overrides):
    task = {
        "task_uid_key": uid,
        "event_uid": "ev1",
        "task_id": "task-1",
        "member_id": "assignment-1",
        "account": ACCOUNT,
        "task_name": "Drive",
        "task_type": "ASSIGNED",
        "status": "unanswered",
        "adults_only": True,
        "event_title": "Training",
        "start": "2026-09-01T16:00:00Z",
        "end": "2026-09-01T17:00:00Z",
        "location": "",
        "address": "",
        "required": 0,
        "assigned_count": 0,
        "co_assignees": [],
        "cancelled": False,
    }
    task.update(overrides)
    return task


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def coordinator(hass):
    """A coordinator holding one unanswered task, with polling stubbed out."""
    entry = MockConfigEntry(version=2, domain=DOMAIN, data=ENTRY_DATA, options={})
    entry.add_to_hass(hass)
    coord = SpondDataUpdateCoordinator(hass, entry)
    coord.data = CoordinatorData(events={"alice": []}, tasks={"alice": [_task()]})
    coord.async_request_refresh = AsyncMock()
    return coord


def _mock_spond(status=200, body="{}"):
    """Stand in for spond_lib.Spond, capturing the PUT it receives."""
    client = MagicMock()
    client.api_url = "https://api.spond.com/core/v1/"
    client.auth_headers = {"Authorization": "Bearer x"}
    client.login = AsyncMock()
    client.clientsession.close = AsyncMock()

    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=body)
    put_ctx = MagicMock()
    put_ctx.__aenter__ = AsyncMock(return_value=response)
    put_ctx.__aexit__ = AsyncMock(return_value=False)
    client.clientsession.put = MagicMock(return_value=put_ctx)
    return client


# ── Responding ───────────────────────────────────────────────────────────────


async def test_accept_puts_to_assignment_endpoint(hass, coordinator) -> None:
    """The response goes to .../tasks/{taskId}/assignments/{memberId}."""
    client = _mock_spond()
    with patch("custom_components.spond_tracker.coordinator.spond_lib.Spond", return_value=client):
        await coordinator.async_respond_to_task("alice", "ev1::Drive", True)

    url = client.clientsession.put.call_args.args[0]
    payload = client.clientsession.put.call_args.kwargs["json"]
    assert url == ("https://api.spond.com/core/v1/sponds/ev1/tasks/task-1/assignments/assignment-1")
    assert payload == {"accepted": True}
    assert coordinator.async_request_refresh.called


async def test_decline_sends_accepted_false(hass, coordinator) -> None:
    client = _mock_spond()
    with patch("custom_components.spond_tracker.coordinator.spond_lib.Spond", return_value=client):
        await coordinator.async_respond_to_task("alice", "ev1::Drive", False)
    assert client.clientsession.put.call_args.kwargs["json"] == {"accepted": False}


async def test_unknown_task_is_reported(hass, coordinator) -> None:
    with pytest.raises(HomeAssistantError, match="No Spond task"):
        await coordinator.async_respond_to_task("alice", "ev1::Nope", True)


async def test_rejected_response_raises(hass, coordinator) -> None:
    client = _mock_spond(status=403, body="forbidden")
    with (
        patch("custom_components.spond_tracker.coordinator.spond_lib.Spond", return_value=client),
        pytest.raises(HomeAssistantError, match="HTTP 403"),
    ):
        await coordinator.async_respond_to_task("alice", "ev1::Drive", True)


async def test_task_without_ids_is_refused(hass, coordinator) -> None:
    """A task seen before ids were recorded cannot be answered blindly."""
    coordinator.data = CoordinatorData(events={"alice": []}, tasks={"alice": [_task(task_id=None)]})
    with pytest.raises(HomeAssistantError, match="missing the account or"):
        await coordinator.async_respond_to_task("alice", "ev1::Drive", True)


async def test_answering_clears_a_snooze(hass, coordinator) -> None:
    coordinator.snoozed = {"ev1::Drive": (dt_util.utcnow() + timedelta(days=1)).isoformat()}
    client = _mock_spond()
    with patch("custom_components.spond_tracker.coordinator.spond_lib.Spond", return_value=client):
        await coordinator.async_respond_to_task("alice", "ev1::Drive", True)
    assert coordinator.snoozed == {}


# ── Snoozing ─────────────────────────────────────────────────────────────────


async def test_snooze_records_deadline(hass, coordinator) -> None:
    until = dt_util.utcnow() + timedelta(hours=4)
    await coordinator.async_snooze_task("alice", "ev1::Drive", until)
    assert coordinator.snoozed["ev1::Drive"] == until.isoformat()


async def test_snooze_in_the_past_clears_it(hass, coordinator) -> None:
    coordinator.snoozed = {"ev1::Drive": (dt_util.utcnow() + timedelta(days=1)).isoformat()}
    await coordinator.async_snooze_task(
        "alice", "ev1::Drive", dt_util.utcnow() - timedelta(seconds=1)
    )
    assert coordinator.snoozed == {}


async def test_snoozing_an_unknown_task_is_reported(hass, coordinator) -> None:
    with pytest.raises(HomeAssistantError, match="No Spond task"):
        await coordinator.async_snooze_task("alice", "ev1::Nope", dt_util.utcnow())


async def test_apply_snoozes_stamps_and_prunes(hass, coordinator) -> None:
    """Live snoozes are stamped; expired ones and orphans are forgotten."""
    future = (dt_util.utcnow() + timedelta(hours=1)).isoformat()
    coordinator.snoozed = {
        "ev1::Drive": future,
        "ev1::Gone": future,  # task no longer exists
        "ev1::Old": (dt_util.utcnow() - timedelta(hours=1)).isoformat(),
    }
    tasks = {"alice": [_task()]}
    coordinator._apply_snoozes(tasks)

    assert tasks["alice"][0]["snoozed_until"] == future
    assert set(coordinator.snoozed) == {"ev1::Drive"}


async def test_apply_snoozes_clears_stamp_when_not_snoozed(hass, coordinator) -> None:
    tasks = {"alice": [_task()]}
    coordinator._apply_snoozes(tasks)
    assert tasks["alice"][0]["snoozed_until"] is None


# ── Sensor bookkeeping ───────────────────────────────────────────────────────


def test_snoozed_task_is_not_outstanding() -> None:
    assert _is_outstanding(_task()) is True
    assert (
        _is_outstanding(_task(snoozed_until=datetime(2099, 1, 1, tzinfo=UTC).isoformat())) is False
    )
    assert _is_outstanding(_task(status="declined")) is False
    assert _is_outstanding(_task(cancelled=True)) is False
