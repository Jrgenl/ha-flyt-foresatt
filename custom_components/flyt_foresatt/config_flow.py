"""Config flow for Flyt Foresatt."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import create_client
from .api import FlytAuthError, FlytError, parse_cookie_header
from .const import CONF_COOKIES, CONF_MUNICIPALITY, DOMAIN, FRONTEND_URL

_LOGGER = logging.getLogger(__name__)

COOKIE_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)
)


class FlytConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Flyt Foresatt."""

    VERSION = 1

    async def _validate(
        self, raw_cookie: str
    ) -> tuple[dict[str, str], str | None, dict[str, str]]:
        """Validate cookies. Returns (cookies, unique_id, errors)."""
        cookies = parse_cookie_header(raw_cookie)
        if not cookies:
            return {}, None, {"base": "invalid_cookie"}
        client = create_client(self.hass, cookies)
        try:
            session = await client.get_session()
            children = await client.get_children()
        except FlytAuthError:
            return {}, None, {"base": "invalid_auth"}
        except FlytError:
            _LOGGER.exception("Could not connect to Flyt Foresatt")
            return {}, None, {"base": "cannot_connect"}
        unique_id = None
        if isinstance(session, dict):
            for key in ("guardianId", "userId", "personId", "id"):
                if session.get(key):
                    unique_id = str(session[key])
                    break
        if unique_id is None:
            ids = sorted(
                str((c.get("school") or {}).get("pupilId") or c.get("firstName"))
                for c in children
            )
            unique_id = "-".join(ids) or None
        return client.cookies, unique_id, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for municipality and session cookie."""
        errors: dict[str, str] = {}
        if user_input is not None:
            municipality = user_input[CONF_MUNICIPALITY].strip().strip("/").lower()
            cookies, unique_id, errors = await self._validate(user_input[CONF_COOKIES])
            if not errors:
                if unique_id:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Flyt Foresatt ({municipality})",
                    data={CONF_MUNICIPALITY: municipality, CONF_COOKIES: cookies},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MUNICIPALITY): str,
                    vol.Required(CONF_COOKIES): COOKIE_SELECTOR,
                }
            ),
            errors=errors,
            description_placeholders={"portal": f"{FRONTEND_URL}/<kommune>"},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle an expired session."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh session cookie."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            cookies, _, errors = await self._validate(user_input[CONF_COOKIES])
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_COOKIES: cookies}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_COOKIES): COOKIE_SELECTOR}),
            errors=errors,
            description_placeholders={
                "portal": f"{FRONTEND_URL}/{entry.data.get(CONF_MUNICIPALITY, '')}"
            },
        )
