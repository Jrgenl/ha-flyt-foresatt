"""Fixtures for Flyt Foresatt tests."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.flyt_foresatt.const import (
    API_URL,
    CONF_COOKIES,
    CONF_MUNICIPALITY,
    DOMAIN,
)

PUPIL_ID = 12345


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Flyt Foresatt (hamar)",
        unique_id="guardian-1",
        data={CONF_MUNICIPALITY: "hamar", CONF_COOKIES: {".AspNetCore.Cookies": "abc"}},
    )


def timetable_for(monday: date) -> list[dict]:
    """A realistic-looking week: lessons Mon-Fri, a school event on Wednesday."""
    days = []
    for offset in range(5):
        day = monday + timedelta(days=offset)
        days.append(
            {
                "day": f"{day.isoformat()}T00:00:00",
                "sessions": [
                    {
                        "sessionStartTime": "08:30:00",
                        "sessionEndTime": "09:15:00",
                        "subjectName": "Norsk",
                        "roomName": "A101",
                        "subjectTeachers": ["Kari Lærer"],
                    },
                    {
                        "sessionStartTime": "13:00:00",
                        "sessionEndTime": "14:00:00",
                        "subjectName": "Matematikk",
                        "roomName": "B2",
                        "subjectTeachers": [{"name": "Per Lærer"}],
                    },
                ],
                "schoolEvents": (
                    [
                        {
                            "eventName": "Aktivitetsdag",
                            "eventDescription": "Ta med matpakke",
                        }
                    ]
                    if offset == 2
                    else []
                ),
            }
        )
    return days


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Mock all API endpoints used by the integration."""
    today = dt_util.now().date()
    monday = today - timedelta(days=today.weekday())
    p = f"{API_URL}vfs/v1/pupils/{PUPIL_ID}"

    aioclient_mock.get(
        f"{API_URL}v1/session",
        json={"guardianId": "guardian-1", "fullName": "Jørgen Test"},
        headers={
            "Set-Cookie": ".AspNetCore.Cookies=refreshed; path=/; secure; httponly"
        },
    )
    aioclient_mock.get(
        f"{API_URL}v2/children",
        json={
            "children": [
                {
                    "firstName": "Ola",
                    "lastName": "Nordmann",
                    "school": {
                        "pupilId": PUPIL_ID,
                        "schoolId": 7,
                        "organizationName": "Hamar skole",
                    },
                },
                {"firstName": "Lillebror", "kindergarten": {"applicationChildId": 99}},
            ],
            "kindergartenPersonRegistryStatus": None,
        },
    )
    aioclient_mock.get(f"{API_URL}vfs/v1/digital-forms/not-answered-count", json=2)
    aioclient_mock.get(
        f"{API_URL}vfs/v1/badge", json=[{"pupilId": PUPIL_ID, "count": 3}]
    )
    # Both weeks share a URL path; serve a timetable covering this and next week.
    aioclient_mock.get(
        f"{p}/timetable",
        json=timetable_for(monday) + timetable_for(monday + timedelta(weeks=1)),
    )
    aioclient_mock.get(f"{p}/notifications/unread-count", json={"unreadCount": 4})
    aioclient_mock.get(
        f"{p}/messages/direct",
        json=[
            {
                "idMessage": 1,
                "title": "Foreldremøte",
                "sender": "Kari",
                "sentDate": "2026-09-20T10:00:00",
                "unreadCount": 1,
            },
            {
                "idMessage": 2,
                "title": "Tur",
                "sender": "Per",
                "sentDate": "2026-09-21T10:00:00",
                "unreadCount": 0,
            },
        ],
    )
    aioclient_mock.get(
        f"{p}/messages/group",
        json=[
            {
                "id": 5,
                "title": "7A",
                "lastMessage": "Husk gymtøy",
                "lastMessageDate": "2026-09-22T08:00:00",
                "unreadMessageCount": 2,
            }
        ],
    )
    aioclient_mock.get(
        f"{p}/absences/years",
        json=[{"id": 2025, "name": "2025/2026", "isCurrent": True}],
    )
    aioclient_mock.get(f"{p}/absences/2025/summary", json={"days": 1, "hours": 2})
    aioclient_mock.get(
        f"{p}/absences/2025",
        json=[
            {"date": "2026-09-01T00:00:00", "subject": "Norsk"},
            {"date": "2026-09-02T00:00:00"},
        ],
    )
    aioclient_mock.get(f"{p}/sfo-presence/details", status=404)
    return aioclient_mock
