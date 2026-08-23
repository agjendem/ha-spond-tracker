"""Tests for the Spond Tracker config flow and options flow."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spond_tracker.config_flow import CannotConnect, InvalidAuth
from custom_components.spond_tracker.const import (
    CONF_ACCOUNTS,
    CONF_EVENT_WINDOW_DAYS,
    CONF_INCLUDE_UNINVITED,
    CONF_MEMBERS,
    CONF_NIGHT_END,
    CONF_NIGHT_POLL_INTERVAL,
    CONF_NIGHT_START,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_UNINVITED_HORIZON_DAYS,
    CONF_USERNAME,
    DEFAULT_EVENT_WINDOW_DAYS,
    DEFAULT_INCLUDE_UNINVITED,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_UNINVITED_HORIZON_DAYS,
    DOMAIN,
)

# ── Test data ────────────────────────────────────────────────────────────────

MOCK_MEMBERS = [
    {"canonical": "alice", "display_name": "Alice Smith"},
    {"canonical": "bob", "display_name": "Bob Jones"},
]

ENTRY_DATA = {
    CONF_ACCOUNTS: [{CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"}],
    CONF_MEMBERS: MOCK_MEMBERS,
}


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading of custom integrations during tests."""
    yield


@pytest.fixture
def mock_setup_entry():
    """Skip actual integration setup so flow tests stay pure."""
    with patch(
        "custom_components.spond_tracker.async_setup_entry",
        return_value=True,
    ):
        yield


@pytest.fixture
def mock_validate(return_value=None):
    """Patch _validate_and_discover to return MOCK_MEMBERS."""
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        return_value=return_value if return_value is not None else MOCK_MEMBERS,
    ) as m:
        yield m


# ── ConfigFlow: user step ─────────────────────────────────────────────────────


async def test_user_step_shows_form(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_user_step_invalid_auth(hass):
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        side_effect=InvalidAuth("bad creds"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_USERNAME: "u@e.com", CONF_PASSWORD: "wrong"},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_step_cannot_connect(hass):
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        side_effect=CannotConnect("timeout"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_USERNAME: "u@e.com", CONF_PASSWORD: "pw"},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_step_unexpected_error(hass):
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        side_effect=RuntimeError("boom"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_USERNAME: "u@e.com", CONF_PASSWORD: "pw"},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_step_success_advances_to_members(hass, mock_validate):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERNAME: "u@e.com", CONF_PASSWORD: "pw"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "members"


async def test_user_step_already_configured(hass, mock_validate, mock_setup_entry):
    # First setup succeeds
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERNAME: "u@e.com", CONF_PASSWORD: "pw"},
    )
    await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_MEMBERS: ["alice"]})

    # Second attempt with same username → abort
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERNAME: "u@e.com", CONF_PASSWORD: "pw"},
    )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


# ── ConfigFlow: members step ──────────────────────────────────────────────────


async def test_members_step_shows_form(hass, mock_validate):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERNAME: "u@e.com", CONF_PASSWORD: "pw"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "members"
    # Both members should appear as options
    schema_keys = list(result["data_schema"].schema.keys())
    assert any(str(k) == CONF_MEMBERS for k in schema_keys)


async def test_members_step_creates_entry(hass, mock_validate, mock_setup_entry):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERNAME: "u@e.com", CONF_PASSWORD: "pw"},
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MEMBERS: ["alice"]}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Spond (u@e.com)"
    data = result2["data"]
    assert data[CONF_ACCOUNTS] == [{CONF_USERNAME: "u@e.com", CONF_PASSWORD: "pw"}]
    assert len(data[CONF_MEMBERS]) == 1
    assert data[CONF_MEMBERS][0]["canonical"] == "alice"


async def test_members_step_all_members_selected(hass, mock_validate, mock_setup_entry):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERNAME: "u@e.com", CONF_PASSWORD: "pw"},
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MEMBERS: ["alice", "bob"]}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert len(result2["data"][CONF_MEMBERS]) == 2


async def test_members_step_no_members_skips_to_entry(hass, mock_setup_entry):
    """If no members are discoverable, entry is created immediately with empty list."""
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_USERNAME: "u@e.com", CONF_PASSWORD: "pw"},
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MEMBERS] == []


# ── OptionsFlow: init step ────────────────────────────────────────────────────


@pytest.fixture
async def config_entry(hass, mock_setup_entry):
    """A pre-configured Spond Tracker entry with one account for options tests."""
    entry = MockConfigEntry(
        version=2,
        domain=DOMAIN,
        title="Spond (u@e.com)",
        data=ENTRY_DATA,
        options={},
        unique_id="u@e.com",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_options_init_shows_form(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_init_saves_poll_interval(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: 60}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_POLL_INTERVAL] == 60


async def test_options_init_default_poll_interval(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    schema = result["data_schema"].schema
    poll_key = next(k for k in schema if str(k) == CONF_POLL_INTERVAL)
    assert poll_key.default() == DEFAULT_POLL_INTERVAL


async def test_options_uninvited_defaults_to_off(hass, config_entry):
    """Opt-in: fetching them multiplies the payload sevenfold."""
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    schema = result["data_schema"].schema
    key = next(k for k in schema if str(k) == CONF_INCLUDE_UNINVITED)
    assert key.default() is DEFAULT_INCLUDE_UNINVITED is False


async def test_options_saves_uninvited_choice(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: 30, CONF_INCLUDE_UNINVITED: True}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_INCLUDE_UNINVITED] is True


async def test_options_uninvited_keeps_previous_choice_as_default(hass, config_entry):
    hass.config_entries.async_update_entry(config_entry, options={CONF_INCLUDE_UNINVITED: True})
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    schema = result["data_schema"].schema
    key = next(k for k in schema if str(k) == CONF_INCLUDE_UNINVITED)
    assert key.default() is True


async def test_options_window_defaults_match_current_behaviour(hass, config_entry):
    """Defaults must reproduce the pre-existing 60-day fetch exactly."""
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    schema = result["data_schema"].schema
    window = next(k for k in schema if str(k) == CONF_EVENT_WINDOW_DAYS)
    horizon = next(k for k in schema if str(k) == CONF_UNINVITED_HORIZON_DAYS)
    assert window.default() == DEFAULT_EVENT_WINDOW_DAYS == 60
    assert horizon.default() == DEFAULT_UNINVITED_HORIZON_DAYS == 14


async def test_options_saves_both_windows(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: 30,
            CONF_INCLUDE_UNINVITED: True,
            CONF_UNINVITED_HORIZON_DAYS: 7,
            CONF_EVENT_WINDOW_DAYS: 90,
        },
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_UNINVITED_HORIZON_DAYS] == 7
    assert result2["data"][CONF_EVENT_WINDOW_DAYS] == 90


async def test_options_windows_keep_previous_values_as_defaults(hass, config_entry):
    hass.config_entries.async_update_entry(
        config_entry,
        options={CONF_EVENT_WINDOW_DAYS: 30, CONF_UNINVITED_HORIZON_DAYS: 5},
    )
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    schema = result["data_schema"].schema
    window = next(k for k in schema if str(k) == CONF_EVENT_WINDOW_DAYS)
    horizon = next(k for k in schema if str(k) == CONF_UNINVITED_HORIZON_DAYS)
    assert window.default() == 30
    assert horizon.default() == 5


async def test_options_night_polling_defaults_to_off(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    schema = result["data_schema"].schema
    night = next(k for k in schema if str(k) == CONF_NIGHT_POLL_INTERVAL)
    assert night.default() == 0


async def test_options_saves_night_polling(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_POLL_INTERVAL: 30,
            CONF_NIGHT_POLL_INTERVAL: 180,
            CONF_NIGHT_START: "22:30:00",
            CONF_NIGHT_END: "06:00:00",
        },
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_NIGHT_POLL_INTERVAL] == 180
    assert result2["data"][CONF_NIGHT_START] == "22:30:00"


# ── OptionsFlow: add account ──────────────────────────────────────────────────


async def test_options_add_account_flow(hass, config_entry):
    """Adding a second account with new members merges them in."""
    new_members = [{"canonical": "carol", "display_name": "Carol White"}]

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        return_value=new_members,
    ):
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL, "action": "add"}
        )
        assert result2["step_id"] == "add_account"

        result3 = await hass.config_entries.options.async_configure(
            result2["flow_id"],
            {CONF_USERNAME: "other@example.com", CONF_PASSWORD: "pw2"},
        )
    # Should land on add_account_members to pick new members
    assert result3["step_id"] == "add_account_members"

    result4 = await hass.config_entries.options.async_configure(
        result3["flow_id"], {CONF_MEMBERS: ["carol"]}
    )
    assert result4["type"] == FlowResultType.CREATE_ENTRY

    updated = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert len(updated.data[CONF_ACCOUNTS]) == 2
    assert any(a[CONF_USERNAME] == "other@example.com" for a in updated.data[CONF_ACCOUNTS])
    assert any(m["canonical"] == "carol" for m in updated.data[CONF_MEMBERS])


async def test_options_add_account_invalid_auth(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        side_effect=InvalidAuth("bad"),
    ):
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL, "action": "add"}
        )
        result3 = await hass.config_entries.options.async_configure(
            result2["flow_id"],
            {CONF_USERNAME: "bad@example.com", CONF_PASSWORD: "wrong"},
        )
    assert result3["type"] == FlowResultType.FORM
    assert result3["errors"] == {"base": "invalid_auth"}


async def test_options_add_duplicate_account_is_noop(hass, config_entry):
    """Adding an already-configured account just saves options without merging."""
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL, "action": "add"}
    )
    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"],
        # Same username as the existing account
        {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "pw"},
    )
    assert result3["type"] == FlowResultType.CREATE_ENTRY
    # Still only one account
    updated = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert len(updated.data[CONF_ACCOUNTS]) == 1


# ── OptionsFlow: remove account ───────────────────────────────────────────────


@pytest.fixture
async def two_account_entry(hass, mock_setup_entry):
    """Entry with two accounts, needed to expose the remove action."""
    data = {
        CONF_ACCOUNTS: [
            {CONF_USERNAME: "a@example.com", CONF_PASSWORD: "pa"},
            {CONF_USERNAME: "b@example.com", CONF_PASSWORD: "pb"},
        ],
        CONF_MEMBERS: [
            {"canonical": "alice", "display_name": "Alice"},
            {"canonical": "bob", "display_name": "Bob"},
        ],
    }
    entry = MockConfigEntry(
        version=2,
        domain=DOMAIN,
        title="Spond (a@example.com)",
        data=data,
        options={},
        unique_id="a@example.com",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_options_remove_account(hass, two_account_entry):
    """Removing one of two accounts keeps members reachable from the remaining account."""
    # After removal, only alice remains (discovered from b@example.com)
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        return_value=[{"canonical": "alice", "display_name": "Alice"}],
    ):
        result = await hass.config_entries.options.async_init(two_account_entry.entry_id)
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL, "action": "remove"},
        )
        assert result2["step_id"] == "remove_account"

        result3 = await hass.config_entries.options.async_configure(
            result2["flow_id"], {"account": "a@example.com"}
        )
    assert result3["type"] == FlowResultType.CREATE_ENTRY

    updated = hass.config_entries.async_get_entry(two_account_entry.entry_id)
    assert len(updated.data[CONF_ACCOUNTS]) == 1
    assert updated.data[CONF_ACCOUNTS][0][CONF_USERNAME] == "b@example.com"
    # bob is gone since he's not reachable from the remaining account
    assert all(m["canonical"] != "bob" for m in updated.data[CONF_MEMBERS])


async def test_options_remove_not_shown_with_single_account(hass, config_entry):
    """The remove action is not offered when there is only one account."""
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    schema = result["data_schema"].schema
    action_key = next((k for k in schema if str(k) == "action"), None)
    if action_key is not None:
        # If action selector exists, "remove" must not be in its options
        selector_cfg = schema[action_key]
        options_in_selector = [
            o if isinstance(o, str) else o.get("value", o)
            for o in (getattr(selector_cfg, "config", {}) or {}).get("options", [])
        ]
        assert "remove" not in options_in_selector


# ── OptionsFlow: manage members ───────────────────────────────────────────────


async def _open_manage_members(hass, entry, discovered):
    """Run the options flow up to the manage_members form."""
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        return_value=discovered,
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        return await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL, "action": "members"},
        )


async def test_options_manage_members_adds_newly_discovered(hass, config_entry):
    """A member with no events at setup time can be added later."""
    discovered = [*MOCK_MEMBERS, {"canonical": "carol", "display_name": "Carol White"}]

    result = await _open_manage_members(hass, config_entry, discovered)
    assert result["step_id"] == "manage_members"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MEMBERS: ["alice", "bob", "carol"]}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY

    updated = hass.config_entries.async_get_entry(config_entry.entry_id)
    canonicals = [m["canonical"] for m in updated.data[CONF_MEMBERS]]
    assert canonicals == ["alice", "bob", "carol"]


async def test_options_manage_members_defaults_to_tracked(hass, config_entry):
    """The form pre-selects exactly the members already tracked."""
    discovered = [*MOCK_MEMBERS, {"canonical": "carol", "display_name": "Carol White"}]

    result = await _open_manage_members(hass, config_entry, discovered)
    schema = result["data_schema"].schema
    members_key = next(k for k in schema if str(k) == CONF_MEMBERS)
    assert members_key.default() == ["alice", "bob"]
    # ...while all three are offered
    assert set(schema[members_key].options) == {"alice", "bob", "carol"}


async def test_options_manage_members_untracks_and_cleans_registry(hass, config_entry):
    """Deselecting a member drops it and removes its entities."""
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{config_entry.entry_id}_bob_events",
        config_entry=config_entry,
        suggested_object_id="spond_bob",
    )

    result = await _open_manage_members(hass, config_entry, MOCK_MEMBERS)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MEMBERS: ["alice"]}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY

    updated = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert [m["canonical"] for m in updated.data[CONF_MEMBERS]] == ["alice"]
    assert (
        ent_reg.async_get_entity_id("sensor", DOMAIN, f"{config_entry.entry_id}_bob_events") is None
    )


async def test_options_manage_members_keeps_tracked_member_without_events(hass, config_entry):
    """A tracked member with no upcoming events stays selectable and tracked."""
    # Only alice is discoverable right now; bob's season is over.
    result = await _open_manage_members(hass, config_entry, [MOCK_MEMBERS[0]])
    schema = result["data_schema"].schema
    members_key = next(k for k in schema if str(k) == CONF_MEMBERS)
    assert set(schema[members_key].options) == {"alice", "bob"}

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MEMBERS: ["alice", "bob"]}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY

    updated = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert [m["canonical"] for m in updated.data[CONF_MEMBERS]] == ["alice", "bob"]


async def test_options_manage_members_keeps_stored_display_name(hass, config_entry):
    """Re-discovery must not rename devices for members already tracked."""
    discovered = [{"canonical": "alice", "display_name": "Alice Renamed"}, MOCK_MEMBERS[1]]

    result = await _open_manage_members(hass, config_entry, discovered)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MEMBERS: ["alice", "bob"]}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY

    updated = hass.config_entries.async_get_entry(config_entry.entry_id)
    alice = next(m for m in updated.data[CONF_MEMBERS] if m["canonical"] == "alice")
    assert alice["display_name"] == "Alice Smith"


async def test_options_manage_members_aborts_when_spond_unreachable(hass, config_entry):
    """No account answered — abort instead of showing an empty member list."""
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        side_effect=CannotConnect("down"),
    ):
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL, "action": "members"},
        )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "cannot_connect"
    # Members left untouched
    updated = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert [m["canonical"] for m in updated.data[CONF_MEMBERS]] == ["alice", "bob"]


async def test_options_manage_members_survives_one_failing_account(hass, two_account_entry):
    """One unreachable account must not hide members from the working one."""
    calls = []

    async def _fake(username, password):
        calls.append(username)
        if username == "a@example.com":
            raise CannotConnect("down")
        return [{"canonical": "bob", "display_name": "Bob"}]

    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        side_effect=_fake,
    ):
        result = await hass.config_entries.options.async_init(two_account_entry.entry_id)
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL, "action": "members"},
        )
    assert result2["step_id"] == "manage_members"
    assert len(calls) == 2


# ── ReauthFlow ────────────────────────────────────────────────────────────────


async def test_reauth_step_shows_form(hass, config_entry):
    """Reauth flow shows the reauth_confirm form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": config_entry.entry_id},
        data=config_entry.data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_invalid_auth(hass, config_entry):
    """Reauth with wrong credentials shows invalid_auth error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": config_entry.entry_id},
        data=config_entry.data,
    )
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        side_effect=InvalidAuth("bad"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "wrong"},
        )
    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_reauth_success_updates_password(hass, config_entry, mock_setup_entry):
    """Successful reauth updates the account password in entry data."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": config_entry.entry_id},
        data=config_entry.data,
    )
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        return_value=MOCK_MEMBERS,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "newpass"},
        )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    updated = hass.config_entries.async_get_entry(config_entry.entry_id)
    account = updated.data[CONF_ACCOUNTS][0]
    assert account[CONF_PASSWORD] == "newpass"


async def test_reauth_single_account_prefills_username(hass, config_entry):
    """Reauth form pre-fills username when there is only one account."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": config_entry.entry_id},
        data=config_entry.data,
    )
    assert result["type"] == FlowResultType.FORM
    schema_keys = list(result["data_schema"].schema.keys())
    username_key = next(k for k in schema_keys if str(k) == CONF_USERNAME)
    assert username_key.default() == "user@example.com"


# ── ReconfigureFlow ───────────────────────────────────────────────────────────


async def test_reconfigure_shows_form(hass, config_entry):
    """Reconfigure flow shows the reconfigure form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": config_entry.entry_id},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"


async def test_reconfigure_invalid_auth(hass, config_entry):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": config_entry.entry_id},
    )
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        side_effect=InvalidAuth("bad"),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "wrong"},
        )
    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_success_updates_password(hass, config_entry, mock_setup_entry):
    """Successful reconfigure updates the account password."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": config_entry.entry_id},
    )
    with patch(
        "custom_components.spond_tracker.config_flow._validate_and_discover",
        return_value=MOCK_MEMBERS,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "user@example.com", CONF_PASSWORD: "brandnew"},
        )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reconfigure_successful"
    updated = hass.config_entries.async_get_entry(config_entry.entry_id)
    assert updated.data[CONF_ACCOUNTS][0][CONF_PASSWORD] == "brandnew"
