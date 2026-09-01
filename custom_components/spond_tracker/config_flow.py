"""Config flow for Spond Tracker."""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from spond import spond as spond_lib

from .const import (
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
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_POLL_INTERVAL,
    DEFAULT_NIGHT_START,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_UNINVITED_HORIZON_DAYS,
    DOMAIN,
)
from .spond_helpers import members_from_events

_LOGGER = logging.getLogger(__name__)


class InvalidAuth(Exception):
    """Raised when Spond rejects the credentials."""


class CannotConnect(Exception):
    """Raised when we can't reach Spond."""


async def _validate_and_discover(username: str, password: str) -> list[dict]:
    """Authenticate with Spond and return one entry per trackable person.

    Deduplicates by first name (canonical): the same child may have separate
    Spond member IDs in different groups, but all collapse to one entry here.
    Returns list[{canonical, display_name}] — no IDs stored.
    """
    s = spond_lib.Spond(username=username, password=password)
    try:
        now = datetime.now(UTC)
        events = await s.get_events(
            min_end=now,
            max_end=now + timedelta(days=90),
            max_events=50,
        )
    except Exception as exc:
        err = str(exc).lower()
        if any(code in err for code in ("401", "403", "unauthorized", "forbidden", "invalid")):
            raise InvalidAuth(str(exc)) from exc
        raise CannotConnect(str(exc)) from exc
    finally:
        with contextlib.suppress(Exception):
            await s.clientsession.close()

    return members_from_events(events)


def _remove_member_registry_entries(
    hass: HomeAssistant, entry: ConfigEntry, canonicals: list[str]
) -> None:
    """Drop entities and devices for members that are no longer tracked."""
    if not canonicals:
        return

    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.unique_id and any(
            ent.unique_id.startswith(f"{entry.entry_id}_{canonical}_") for canonical in canonicals
        ):
            ent_reg.async_remove(ent.entity_id)
            _LOGGER.debug("Removed entity %s (member no longer tracked)", ent.entity_id)

    dev_reg = dr.async_get(hass)
    for canonical in canonicals:
        device = dev_reg.async_get_device(identifiers={(DOMAIN, f"{entry.entry_id}_{canonical}")})
        if device:
            dev_reg.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
            _LOGGER.debug("Removed device for member %s (no longer tracked)", canonical)


class SpondTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 2

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""
        self._discovered_members: list[dict] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> dict:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._discovered_members = await _validate_and_discover(
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Spond discovery")
                errors["base"] = "cannot_connect"
            else:
                self._username = user_input[CONF_USERNAME]
                self._password = user_input[CONF_PASSWORD]
                await self.async_set_unique_id(self._username.lower())
                self._abort_if_unique_id_configured()
                return await self.async_step_members()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_members(self, user_input: dict[str, Any] | None = None) -> dict:
        if not self._discovered_members:
            _LOGGER.warning(
                "No on-behalf-of members found for %s; "
                "make sure the account has upcoming events in Spond.",
                self._username,
            )
            return self.async_create_entry(
                title=f"Spond ({self._username})",
                data={
                    CONF_ACCOUNTS: [{CONF_USERNAME: self._username, CONF_PASSWORD: self._password}],
                    CONF_MEMBERS: [],
                },
            )

        if user_input is not None:
            selected = user_input.get(CONF_MEMBERS, [])
            selected_members = [m for m in self._discovered_members if m["canonical"] in selected]
            return self.async_create_entry(
                title=f"Spond ({self._username})",
                data={
                    CONF_ACCOUNTS: [{CONF_USERNAME: self._username, CONF_PASSWORD: self._password}],
                    CONF_MEMBERS: selected_members,
                },
            )

        options = {m["canonical"]: m["display_name"] for m in self._discovered_members}
        default_selection = list(options.keys())

        return self.async_show_form(
            step_id="members",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MEMBERS, default=default_selection): cv.multi_select(options),
                }
            ),
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> dict:
        """Handle reauth when polling detects an auth failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> dict:
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        accounts = entry.data.get(CONF_ACCOUNTS, [])
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                await _validate_and_discover(username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during reauth for %s", username)
                errors["base"] = "cannot_connect"
            else:
                updated_accounts = [
                    {**acc, CONF_PASSWORD: password} if acc[CONF_USERNAME] == username else acc
                    for acc in accounts
                ]
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_ACCOUNTS: updated_accounts},
                    reason="reauth_successful",
                )

        default_username = accounts[0][CONF_USERNAME] if len(accounts) == 1 else ""
        account_list = "\n" + "\n".join(f"- {a[CONF_USERNAME]}" for a in accounts)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=default_username): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            description_placeholders={"accounts": account_list},
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> dict:
        """Allow updating account credentials without removing the integration."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        accounts = entry.data.get(CONF_ACCOUNTS, [])
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                await _validate_and_discover(username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during reconfigure for %s", username)
                errors["base"] = "cannot_connect"
            else:
                updated_accounts = [
                    {**acc, CONF_PASSWORD: password} if acc[CONF_USERNAME] == username else acc
                    for acc in accounts
                ]
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_ACCOUNTS: updated_accounts},
                    reason="reconfigure_successful",
                )

        default_username = accounts[0][CONF_USERNAME] if len(accounts) == 1 else vol.UNDEFINED
        username_field: Any = (
            vol.In({a[CONF_USERNAME]: a[CONF_USERNAME] for a in accounts})
            if len(accounts) > 1
            else str
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=default_username): username_field,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SpondTrackerOptionsFlow:
        return SpondTrackerOptionsFlow()


class SpondTrackerOptionsFlow(OptionsFlow):
    """Handle options: poll interval, tracked members, and Spond accounts."""

    def __init__(self) -> None:
        self._pending_options: dict[str, Any] = {}
        self._new_account: dict[str, str] = {}
        self._new_members: list[dict] = []
        self._member_choices: list[dict] = []

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> dict:
        if user_input is not None:
            action = user_input.pop("action", None)
            if action == "add":
                self._pending_options = user_input
                return await self.async_step_add_account()
            if action == "remove":
                self._pending_options = user_input
                return await self.async_step_remove_account()
            if action == "members":
                self._pending_options = user_input
                return await self.async_step_manage_members()
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options
        accounts = self.config_entry.data.get(CONF_ACCOUNTS, [])
        account_labels = (
            "\n" + "\n".join(f"- {a[CONF_USERNAME]}" for a in accounts) if accounts else "—"
        )

        action_values = ["members", "add"]
        if len(accounts) > 1:
            action_values.append("remove")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=current.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                    ): vol.All(int, vol.Range(min=5, max=1440)),
                    vol.Required(
                        CONF_NIGHT_POLL_INTERVAL,
                        default=current.get(CONF_NIGHT_POLL_INTERVAL, DEFAULT_NIGHT_POLL_INTERVAL),
                    ): vol.All(int, vol.Range(min=0, max=1440)),
                    vol.Required(
                        CONF_NIGHT_START,
                        default=current.get(CONF_NIGHT_START, DEFAULT_NIGHT_START),
                    ): selector.TimeSelector(),
                    vol.Required(
                        CONF_NIGHT_END,
                        default=current.get(CONF_NIGHT_END, DEFAULT_NIGHT_END),
                    ): selector.TimeSelector(),
                    vol.Required(
                        CONF_INCLUDE_UNINVITED,
                        default=current.get(CONF_INCLUDE_UNINVITED, DEFAULT_INCLUDE_UNINVITED),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_UNINVITED_HORIZON_DAYS,
                        default=current.get(
                            CONF_UNINVITED_HORIZON_DAYS, DEFAULT_UNINVITED_HORIZON_DAYS
                        ),
                    ): vol.All(int, vol.Range(min=1, max=60)),
                    vol.Required(
                        CONF_EVENT_WINDOW_DAYS,
                        default=current.get(CONF_EVENT_WINDOW_DAYS, DEFAULT_EVENT_WINDOW_DAYS),
                    ): vol.All(int, vol.Range(min=1, max=180)),
                    vol.Optional("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=action_values,
                            translation_key="action",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={"accounts": account_labels},
        )

    async def async_step_add_account(self, user_input: dict[str, Any] | None = None) -> dict:
        errors: dict[str, str] = {}
        if user_input is not None:
            new_username = user_input[CONF_USERNAME]
            new_password = user_input[CONF_PASSWORD]

            existing_accounts = self.config_entry.data.get(CONF_ACCOUNTS, [])
            if any(a[CONF_USERNAME] == new_username for a in existing_accounts):
                # Account already present — just save options and reload
                return self.async_create_entry(title="", data=self._pending_options)

            try:
                new_members = await _validate_and_discover(new_username, new_password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error adding Spond account %s", new_username)
                errors["base"] = "cannot_connect"
            else:
                existing_canonicals = {
                    m["canonical"] for m in self.config_entry.data.get(CONF_MEMBERS, [])
                }
                self._new_account = {CONF_USERNAME: new_username, CONF_PASSWORD: new_password}
                self._new_members = [
                    m for m in new_members if m["canonical"] not in existing_canonicals
                ]
                return await self.async_step_add_account_members()

        return self.async_show_form(
            step_id="add_account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_add_account_members(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        existing_accounts = self.config_entry.data.get(CONF_ACCOUNTS, [])
        existing_members = list(self.config_entry.data.get(CONF_MEMBERS, []))

        def _save(selected: list[dict]) -> dict:
            updated_accounts = [*existing_accounts, self._new_account]
            merged = existing_members + selected
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_ACCOUNTS: updated_accounts,
                    CONF_MEMBERS: merged,
                },
            )
            _LOGGER.info(
                "Added Spond account %s; new members: %s",
                self._new_account.get(CONF_USERNAME),
                [m["canonical"] for m in selected],
            )
            return self.async_create_entry(title="", data=self._pending_options)

        if not self._new_members:
            # No new members to pick — just add the account
            return _save([])

        if user_input is not None:
            chosen = user_input.get(CONF_MEMBERS, [])
            selected = [m for m in self._new_members if m["canonical"] in chosen]
            return _save(selected)

        options = {m["canonical"]: m["display_name"] for m in self._new_members}
        return self.async_show_form(
            step_id="add_account_members",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MEMBERS, default=list(options)): cv.multi_select(options),
                }
            ),
        )

    async def _discover_across_accounts(self) -> tuple[list[dict], bool]:
        """Re-discover trackable members from every configured account.

        Returns the merged, deduplicated member list and whether at least one
        account answered — an account that fails is skipped rather than
        aborting the whole flow.
        """
        merged: dict[str, dict] = {}
        any_fetch_ok = False
        for acc in self.config_entry.data.get(CONF_ACCOUNTS, []):
            try:
                found = await _validate_and_discover(acc[CONF_USERNAME], acc[CONF_PASSWORD])
            except Exception:
                _LOGGER.warning(
                    "Could not fetch members from %s while managing tracked members",
                    acc[CONF_USERNAME],
                )
                continue
            any_fetch_ok = True
            for m in found:
                merged.setdefault(m["canonical"], m)
        return sorted(merged.values(), key=lambda m: m["display_name"]), any_fetch_ok

    async def async_step_manage_members(self, user_input: dict[str, Any] | None = None) -> dict:
        """Change which members are tracked, without re-adding the account.

        Members are only discovered from events, so someone with no upcoming
        events at setup time never appeared in the initial selection. This step
        re-discovers across all accounts so they can be picked up later.
        """
        tracked = list(self.config_entry.data.get(CONF_MEMBERS, []))
        tracked_by_canonical = {m["canonical"]: m for m in tracked}

        if user_input is not None:
            chosen = set(user_input.get(CONF_MEMBERS, []))
            # Keep the stored display_name for members already tracked, so
            # device and entity names stay stable across this flow.
            selected = [
                tracked_by_canonical.get(m["canonical"], m)
                for m in self._member_choices
                if m["canonical"] in chosen
            ]
            dropped = [c for c in tracked_by_canonical if c not in chosen]
            _remove_member_registry_entries(self.hass, self.config_entry, dropped)
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, CONF_MEMBERS: selected},
            )
            _LOGGER.info(
                "Tracked Spond members updated: %s (no longer tracked: %s)",
                [m["canonical"] for m in selected],
                dropped,
            )
            return self.async_create_entry(title="", data=self._pending_options)

        discovered, any_fetch_ok = await self._discover_across_accounts()
        if not any_fetch_ok:
            return self.async_abort(reason="cannot_connect")

        # Already-tracked members stay on the list even when they have no
        # upcoming events right now — a quiet season must not silently drop them.
        known = {m["canonical"] for m in tracked}
        choices = tracked + [m for m in discovered if m["canonical"] not in known]
        self._member_choices = sorted(choices, key=lambda m: m["display_name"])

        options = {m["canonical"]: m["display_name"] for m in self._member_choices}
        return self.async_show_form(
            step_id="manage_members",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MEMBERS, default=list(tracked_by_canonical)): cv.multi_select(
                        options
                    ),
                }
            ),
        )

    async def async_step_remove_account(self, user_input: dict[str, Any] | None = None) -> dict:
        accounts = self.config_entry.data.get(CONF_ACCOUNTS, [])

        if user_input is not None:
            to_remove = user_input["account"]
            remaining = [a for a in accounts if a[CONF_USERNAME] != to_remove]

            current_members = list(self.config_entry.data.get(CONF_MEMBERS, []))
            remaining_canonicals: set[str] = set()
            any_fetch_ok = False
            for acc in remaining:
                try:
                    fetched = await _validate_and_discover(acc[CONF_USERNAME], acc[CONF_PASSWORD])
                    remaining_canonicals.update(m["canonical"] for m in fetched)
                    any_fetch_ok = True
                except Exception:
                    _LOGGER.warning(
                        "Could not fetch members from %s during account removal; keeping existing members",
                        acc[CONF_USERNAME],
                    )

            if any_fetch_ok:
                kept = [m for m in current_members if m["canonical"] in remaining_canonicals]
                removed_names = [
                    m["canonical"]
                    for m in current_members
                    if m["canonical"] not in remaining_canonicals
                ]
            else:
                kept = current_members
                removed_names = []

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, CONF_ACCOUNTS: remaining, CONF_MEMBERS: kept},
            )

            _remove_member_registry_entries(self.hass, self.config_entry, removed_names)

            _LOGGER.info(
                "Removed Spond account %s; removed members: %s",
                to_remove,
                removed_names,
            )
            return self.async_create_entry(title="", data=self._pending_options)

        account_options = {a[CONF_USERNAME]: a[CONF_USERNAME] for a in accounts}
        return self.async_show_form(
            step_id="remove_account",
            data_schema=vol.Schema(
                {
                    vol.Required("account"): vol.In(account_options),
                }
            ),
        )
