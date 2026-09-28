"""Data update coordinator for Flyt Foresatt."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import FlytAuthError, FlytClient, FlytError, FlytNotFoundError
from .const import CONF_COOKIES, DEFAULT_SCAN_INTERVAL, DOMAIN, TIMETABLE_WEEKS

_LOGGER = logging.getLogger(__name__)

FlytConfigEntry = ConfigEntry["FlytCoordinator"]


@dataclass(slots=True)
class Lesson:
    """A single lesson in the timetable."""

    start: datetime
    end: datetime
    subject: str
    room: str | None = None
    teachers: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SchoolEvent:
    """An all-day school event from the timetable."""

    day: date
    name: str
    description: str | None = None


@dataclass(slots=True)
class ChildData:
    """Everything we know about one child."""

    key: str
    name: str
    first_name: str
    pupil_id: int | str | None
    school_name: str | None
    lessons: list[Lesson] = field(default_factory=list)
    school_events: list[SchoolEvent] = field(default_factory=list)
    unread_notifications: int | None = None
    direct_messages: list[dict[str, Any]] | None = None
    group_messages: list[dict[str, Any]] | None = None
    absence_summary: Any = None
    absences: list[dict[str, Any]] | None = None
    sfo_today: Any = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def unread_messages(self) -> int | None:
        """Total unread direct + group messages."""
        if self.direct_messages is None and self.group_messages is None:
            return None
        direct = sum(_as_int(m.get("unreadCount")) for m in self.direct_messages or [])
        group = sum(
            _as_int(m.get("unreadMessageCount")) for m in self.group_messages or []
        )
        return direct + group

    def lessons_on(self, day: date) -> list[Lesson]:
        """Lessons on a given local date, sorted by start."""
        return sorted(
            (lesson for lesson in self.lessons if lesson.start.date() == day),
            key=lambda lesson: lesson.start,
        )


@dataclass(slots=True)
class FlytData:
    """Coordinator payload."""

    guardian_name: str | None
    children: dict[str, ChildData]
    unanswered_forms: int | None
    badges: Any


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    if isinstance(value, dict):
        for key in ("count", "unreadCount", "notAnsweredCount", "value", "total"):
            if key in value:
                return _as_int(value[key])
    return 0


def _as_list(value: Any, *keys: str) -> list[dict[str, Any]]:
    """Return a list of dicts from a response that may or may not be wrapped."""
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    if isinstance(value, dict):
        for key in (*keys, "items", "data", "results"):
            if isinstance(value.get(key), list):
                return [v for v in value[key] if isinstance(v, dict)]
    return []


def _parse_day(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_time(value: Any) -> time | None:
    """Parse ``HH:mm[:ss]`` (the API uses TimeSpan strings) or a full datetime."""
    if not value:
        return None
    text = str(value)
    if "T" in text:
        text = text.split("T", 1)[1]
    try:
        return time.fromisoformat(text[:8])
    except ValueError:
        return None


def _teacher_names(value: Any) -> list[str]:
    names: list[str] = []
    for item in value or []:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or " ".join(
                p for p in (item.get("firstName"), item.get("lastName")) if p
            )
            if name:
                names.append(name)
    return names


def parse_timetable(data: Any) -> tuple[list[Lesson], list[SchoolEvent]]:
    """Parse a timetable response: a list of ``{day, sessions, schoolEvents}``."""
    tz = dt_util.get_default_time_zone()
    lessons: list[Lesson] = []
    events: list[SchoolEvent] = []
    for day_item in _as_list(data, "days", "timetable", "timetableDays"):
        day = _parse_day(day_item.get("day") or day_item.get("date"))
        if day is None:
            continue
        for session in day_item.get("sessions") or []:
            start_t = _parse_time(session.get("sessionStartTime"))
            end_t = _parse_time(session.get("sessionEndTime"))
            if start_t is None or end_t is None:
                continue
            lessons.append(
                Lesson(
                    start=datetime.combine(day, start_t, tzinfo=tz),
                    end=datetime.combine(day, end_t, tzinfo=tz),
                    subject=session.get("subjectName") or "Time",
                    room=session.get("roomName"),
                    teachers=_teacher_names(session.get("subjectTeachers")),
                    raw=session,
                )
            )
        for event in day_item.get("schoolEvents") or []:
            events.append(
                SchoolEvent(
                    day=day,
                    name=event.get("eventName") or "Hendelse",
                    description=event.get("eventDescription"),
                )
            )
    return lessons, events


def _pick_current_year(years: Any) -> Any:
    """Pick the id of the current school year from ``absences/years``."""
    items = _as_list(years, "years", "schoolYears")
    if not items:
        # Might be a plain list of ids/names.
        if isinstance(years, list) and years:
            return years[-1] if not isinstance(years[-1], dict) else None
        return None
    today = dt_util.now().date()
    for item in items:
        if item.get("isCurrent") or item.get("current") or item.get("isActive"):
            break
        start = _parse_day(item.get("startDate") or item.get("from"))
        end = _parse_day(item.get("endDate") or item.get("to"))
        if start and end and start <= today <= end:
            break
    else:
        item = items[0]
    for key in ("id", "schoolYearId", "yearId", "value", "name"):
        if item.get(key) is not None:
            return item[key]
    return None


class FlytCoordinator(DataUpdateCoordinator[FlytData]):
    """Fetches data for all children."""

    config_entry: FlytConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: FlytConfigEntry, client: FlytClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client

    async def _optional(self, label: str, coro: Any) -> Any:
        """Await an optional endpoint; missing features must not break updates."""
        try:
            return await coro
        except FlytAuthError:
            raise
        except FlytNotFoundError:
            _LOGGER.debug("%s: not available", label)
        except FlytError as err:
            _LOGGER.debug("%s failed: %s", label, err)
        return None

    async def _fetch_child(self, child: dict[str, Any]) -> ChildData | None:
        school = child.get("school") or {}
        pupil_id = school.get("pupilId") or child.get("pupilId")
        first_name = child.get("firstName") or child.get("name") or "Barn"
        name = (
            child.get("fullName")
            or " ".join(p for p in (child.get("firstName"), child.get("lastName")) if p)
            or first_name
        )
        if pupil_id is None:
            # Kindergarten-only child: Flyt Foresatt for barnehage is not supported yet.
            _LOGGER.debug("Skipping child without school pupilId: %s", first_name)
            return None

        today = dt_util.now().date()
        monday = today - timedelta(days=today.weekday())
        weeks = [monday + timedelta(weeks=i) for i in range(TIMETABLE_WEEKS)]

        results = await asyncio.gather(
            *(
                self._optional("timetable", self.client.get_timetable(pupil_id, w))
                for w in weeks
            ),
            self._optional(
                "notifications", self.client.get_notifications_unread_count(pupil_id)
            ),
            self._optional(
                "direct messages", self.client.get_direct_messages(pupil_id)
            ),
            self._optional("group messages", self.client.get_group_messages(pupil_id)),
            self._optional("absence years", self.client.get_absence_years(pupil_id)),
            self._optional("sfo", self.client.get_sfo_presence(pupil_id, today)),
        )
        timetables = results[: len(weeks)]
        notif, direct, group, years, sfo = results[len(weeks) :]

        lessons: list[Lesson] = []
        events: list[SchoolEvent] = []
        seen: set[tuple[datetime, str]] = set()
        for timetable in timetables:
            week_lessons, week_events = parse_timetable(timetable)
            for lesson in week_lessons:
                if (lesson.start, lesson.subject) not in seen:
                    seen.add((lesson.start, lesson.subject))
                    lessons.append(lesson)
            for event in week_events:
                if event not in events:
                    events.append(event)

        absence_summary = absences = None
        year_id = _pick_current_year(years)
        if year_id is not None:
            absence_summary, absence_list = await asyncio.gather(
                self._optional(
                    "absence summary",
                    self.client.get_absence_summary(pupil_id, year_id),
                ),
                self._optional("absences", self.client.get_absences(pupil_id, year_id)),
            )
            if absence_list is not None:
                absences = _as_list(absence_list, "absences", "absenceList")

        return ChildData(
            key=str(pupil_id),
            name=name,
            first_name=first_name,
            pupil_id=pupil_id,
            school_name=school.get("organizationName"),
            lessons=lessons,
            school_events=events,
            unread_notifications=None if notif is None else _as_int(notif),
            direct_messages=None
            if direct is None
            else _as_list(direct, "conversations", "messages"),
            group_messages=None
            if group is None
            else _as_list(group, "conversations", "messages"),
            absence_summary=absence_summary,
            absences=absences,
            sfo_today=sfo,
            raw={
                "child": child,
                "timetable": timetables,
                "notifications_unread": notif,
                "direct_messages": direct,
                "group_messages": group,
                "absence_years": years,
                "absence_summary": absence_summary,
                "sfo_today": sfo,
            },
        )

    async def _async_update_data(self) -> FlytData:
        try:
            session = await self.client.get_session()
            children_raw = await self.client.get_children()
            forms, badges = await asyncio.gather(
                self._optional("forms", self.client.get_digital_forms_not_answered()),
                self._optional("badges", self.client.get_badges()),
            )
            children = await asyncio.gather(
                *(self._fetch_child(c) for c in children_raw)
            )
        except FlytAuthError as err:
            raise ConfigEntryAuthFailed(
                "Økten i Flyt Foresatt er utløpt – logg inn på nytt"
            ) from err
        except FlytError as err:
            raise UpdateFailed(str(err)) from err
        finally:
            self._persist_cookies()

        guardian = None
        if isinstance(session, dict):
            guardian = session.get("fullName") or session.get("name")
        return FlytData(
            guardian_name=guardian,
            children={c.key: c for c in children if c is not None},
            unanswered_forms=None if forms is None else _as_int(forms),
            badges=badges,
        )

    def _persist_cookies(self) -> None:
        """Store refreshed session cookies so they survive restarts."""
        if not self.client.cookies_changed:
            return
        self.client.cookies_changed = False
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_COOKIES: self.client.cookies},
        )
