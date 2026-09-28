"""Tests for the config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.flyt_foresatt.const import API_URL, CONF_COOKIES, DOMAIN


async def test_user_flow(hass: HomeAssistant, mock_api: AiohttpClientMocker) -> None:
    """Pasting a valid cookie creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "municipality": " Hamar/ ",
            "cookies": "Cookie: .AspNetCore.Cookies=abc; other=1",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Flyt Foresatt (hamar)"
    assert result["data"]["municipality"] == "hamar"
    assert result["data"][CONF_COOKIES] == {
        ".AspNetCore.Cookies": "refreshed",
        "other": "1",
    }
    assert result["result"].unique_id == "guardian-1"


async def test_user_flow_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Invalid input shows errors."""
    aioclient_mock.get(f"{API_URL}v1/session", status=401)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"municipality": "hamar", "cookies": "nothing here"}
    )
    assert result["errors"] == {"base": "invalid_cookie"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"municipality": "hamar", "cookies": "a=b"}
    )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AiohttpClientMocker
) -> None:
    """Reauth replaces the cookies."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cookies": ".AspNetCore.Cookies=new"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_COOKIES] == {".AspNetCore.Cookies": "refreshed"}
