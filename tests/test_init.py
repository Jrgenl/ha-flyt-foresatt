"""Tests for setup, sensors and calendar."""

from __future__ import annotations

from datetime import datetime, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.flyt_foresatt.const import API_URL, CONF_COOKIES


@pytest.fixture(autouse=True)
async def _set_time_zone(hass: HomeAssistant) -> None:
    await hass.config.async_set_time_zone("Europe/Oslo")


async def test_setup_and_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_api: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Entities are created for the school child with correct values."""
    # A Tuesday at 10:00 local time.
    freezer.move_to(
        datetime(2026, 9, 29, 10, 0, tzinfo=dt_util.get_time_zone("Europe/Oslo"))
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.ola_unread_messages").state == "3"
    attrs = hass.states.get("sensor.ola_unread_messages").attributes
    assert attrs["latest"][0]["title"] == "7A"
    assert hass.states.get("sensor.ola_unread_announcements").state == "4"

    next_lesson = hass.states.get("sensor.ola_next_lesson")
    assert next_lesson.state == "Matematikk"
    assert next_lesson.attributes["room"] == "B2"
    assert next_lesson.attributes["teachers"] == ["Per Lærer"]

    assert (
        hass.states.get("sensor.ola_school_starts_today").state
        == "2026-09-29T06:30:00+00:00"
    )
    assert (
        hass.states.get("sensor.ola_school_ends_today").state
        == "2026-09-29T12:00:00+00:00"
    )
    nxt = hass.states.get("sensor.ola_next_school_day_starts")
    assert nxt.state == "2026-09-30T06:30:00+00:00"
    assert nxt.attributes["lessons"] == ["Norsk", "Matematikk"]

    absences = hass.states.get("sensor.ola_absences_this_school_year")
    assert absences.state == "2"
    assert absences.attributes["summary"] == {"days": 1, "hours": 2}

    assert hass.states.get("sensor.ola_after_school_today").state == "unknown"
    assert hass.states.get("sensor.flyt_foresatt_hamar_unanswered_forms").state == "2"

    # Kindergarten-only child gets no entities.
    assert hass.states.get("sensor.lillebror_unread_messages") is None

    cal = hass.states.get("calendar.ola_timetable")
    assert cal.attributes["message"] == "Matematikk"
    start = dt_util.now().replace(hour=0, minute=0)
    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "entity_id": "calendar.ola_timetable",
            "start_date_time": start,
            "end_date_time": start + timedelta(days=2),
        },
        blocking=True,
        return_response=True,
    )
    summaries = [e["summary"] for e in events["calendar.ola_timetable"]["events"]]
    assert summaries == ["Norsk", "Matematikk", "Aktivitetsdag", "Norsk", "Matematikk"]

    # Refreshed cookie from Set-Cookie is persisted.
    assert config_entry.data[CONF_COOKIES] == {".AspNetCore.Cookies": "refreshed"}


async def test_expired_session_starts_reauth(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A 401 triggers a reauth flow."""
    aioclient_mock.get(f"{API_URL}v1/session", status=401)
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]
