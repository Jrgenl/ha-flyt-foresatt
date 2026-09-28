"""Diagnostics for Flyt Foresatt (raw API responses, redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_COOKIES
from .coordinator import FlytConfigEntry

TO_REDACT = {
    CONF_COOKIES,
    "nin",
    "ssn",
    "birthNumber",
    "nationalIdentityNumber",
    "personalIdentityNumber",
    "email",
    "phone",
    "mobilePhone",
    "phoneNumber",
    "address",
    "streetAddress",
    "photoUrl",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FlytConfigEntry
) -> dict[str, Any]:
    """Return diagnostics, including raw responses to help map the API."""
    data = entry.runtime_data.data
    return async_redact_data(
        {
            "entry": dict(entry.data),
            "guardian_name": data.guardian_name,
            "unanswered_forms": data.unanswered_forms,
            "badges": data.badges,
            "children": {key: child.raw for key, child in data.children.items()},
        },
        TO_REDACT,
    )
