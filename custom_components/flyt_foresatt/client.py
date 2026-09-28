"""Helper to create the API client."""

from __future__ import annotations

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import FlytClient


def create_client(hass: HomeAssistant, cookies: dict[str, str]) -> FlytClient:
    """Create an API client with its own (cookie-less) HTTP session."""
    session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
    return FlytClient(session, cookies)
