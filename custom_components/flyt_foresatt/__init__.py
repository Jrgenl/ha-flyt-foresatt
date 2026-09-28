"""The Flyt Foresatt integration."""

from __future__ import annotations

import aiohttp

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import FlytClient
from .const import CONF_COOKIES
from .coordinator import FlytConfigEntry, FlytCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]


def create_client(hass: HomeAssistant, cookies: dict[str, str]) -> FlytClient:
    """Create an API client with its own (cookie-less) HTTP session."""
    session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
    return FlytClient(session, cookies)


async def async_setup_entry(hass: HomeAssistant, entry: FlytConfigEntry) -> bool:
    """Set up Flyt Foresatt from a config entry."""
    client = create_client(hass, entry.data[CONF_COOKIES])
    coordinator = FlytCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FlytConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
