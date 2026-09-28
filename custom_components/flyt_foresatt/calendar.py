"""Timetable calendar for Flyt Foresatt."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import FlytConfigEntry, FlytCoordinator
from .entity import FlytChildEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlytConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one timetable calendar per child."""
    coordinator = entry.runtime_data
    async_add_entities(
        FlytTimetableCalendar(coordinator, key) for key in coordinator.data.children
    )


class FlytTimetableCalendar(FlytChildEntity, CalendarEntity):
    """Lessons and school events as a calendar."""

    _attr_translation_key = "timetable"

    def __init__(self, coordinator: FlytCoordinator, child_key: str) -> None:
        """Initialize the calendar."""
        super().__init__(coordinator, child_key, "timetable")

    def _events(self) -> list[CalendarEvent]:
        child = self.child
        if child is None:
            return []
        events = [
            CalendarEvent(
                start=lesson.start,
                end=lesson.end,
                summary=lesson.subject,
                location=lesson.room,
                description=", ".join(lesson.teachers) or None,
            )
            for lesson in child.lessons
        ]
        events.extend(
            CalendarEvent(
                start=event.day,
                end=event.day + timedelta(days=1),
                summary=event.name,
                description=event.description,
            )
            for event in child.school_events
        )
        return sorted(events, key=lambda e: e.start_datetime_local)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next event."""
        now = dt_util.now()
        for event in self._events():
            if event.end_datetime_local > now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events in a time range (only fetched weeks are known)."""
        return [
            e
            for e in self._events()
            if e.end_datetime_local > start_date and e.start_datetime_local < end_date
        ]
