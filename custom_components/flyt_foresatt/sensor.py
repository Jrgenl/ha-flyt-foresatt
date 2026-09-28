"""Sensors for Flyt Foresatt."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import ChildData, FlytConfigEntry, FlytCoordinator, Lesson
from .entity import FlytAccountEntity, FlytChildEntity

PARALLEL_UPDATES = 0


def _lesson_attrs(lesson: Lesson | None) -> dict[str, Any]:
    if lesson is None:
        return {}
    return {
        "subject": lesson.subject,
        "start": lesson.start.isoformat(),
        "end": lesson.end.isoformat(),
        "room": lesson.room,
        "teachers": lesson.teachers,
    }


def _next_lesson(child: ChildData) -> Lesson | None:
    now = dt_util.now()
    upcoming = sorted(
        (les for les in child.lessons if les.end > now), key=lambda les: les.start
    )
    return upcoming[0] if upcoming else None


def _next_school_day(child: ChildData) -> list[Lesson]:
    """Lessons of the next school day after today."""
    today = dt_util.now().date()
    days = sorted(
        {les.start.date() for les in child.lessons if les.start.date() > today}
    )
    return child.lessons_on(days[0]) if days else []


def _first_start(lessons: list[Lesson]) -> datetime | None:
    return lessons[0].start if lessons else None


def _last_end(lessons: list[Lesson]) -> datetime | None:
    return max(les.end for les in lessons) if lessons else None


def _conversations(child: ChildData) -> dict[str, Any]:
    items = []
    for conv in child.direct_messages or []:
        items.append(
            {
                "type": "direct",
                "title": conv.get("title") or conv.get("subject"),
                "sender": conv.get("sender") or conv.get("senderName"),
                "sent": conv.get("sentDate"),
                "unread": conv.get("unreadCount") or 0,
            }
        )
    for conv in child.group_messages or []:
        items.append(
            {
                "type": "group",
                "title": conv.get("title") or conv.get("name"),
                "last_message": conv.get("lastMessage"),
                "sent": conv.get("lastMessageDate"),
                "unread": conv.get("unreadMessageCount") or 0,
            }
        )
    items.sort(key=lambda i: str(i.get("sent") or ""), reverse=True)
    return {"latest": items[:10]}


def _sfo_state(child: ChildData) -> str | None:
    """Best-effort SFO status for today from ``sfo-presence/details``."""
    data = child.sfo_today
    if data is None:
        return None
    today = dt_util.now().date().isoformat()
    days = (
        data
        if isinstance(data, list)
        else (
            data.get("days") or data.get("presences") or [data]
            if isinstance(data, dict)
            else []
        )
    )
    for day in days:
        if not isinstance(day, dict) or str(day.get("date", today))[:10] != today:
            continue
        afternoon = day.get("afternoonPresence") or {}
        morning = day.get("morningPresence") or {}
        if (afternoon.get("checkOut") or {}).get("time"):
            return "sjekket_ut"
        if afternoon.get("time") or morning.get("time"):
            return "til_stede"
        return "ikke_registrert"
    return "ingen_sfo_i_dag"


@dataclass(frozen=True, kw_only=True)
class ChildSensorDescription(SensorEntityDescription):
    """Describes a child sensor."""

    value_fn: Callable[[ChildData], Any]
    attrs_fn: Callable[[ChildData], dict[str, Any]] | None = None


CHILD_SENSORS: tuple[ChildSensorDescription, ...] = (
    ChildSensorDescription(
        key="unread_messages",
        translation_key="unread_messages",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.unread_messages,
        attrs_fn=_conversations,
    ),
    ChildSensorDescription(
        key="unread_notifications",
        translation_key="unread_notifications",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: c.unread_notifications,
    ),
    ChildSensorDescription(
        key="next_lesson",
        translation_key="next_lesson",
        value_fn=lambda c: les.subject if (les := _next_lesson(c)) else None,
        attrs_fn=lambda c: _lesson_attrs(_next_lesson(c)),
    ),
    ChildSensorDescription(
        key="school_start_today",
        translation_key="school_start_today",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: _first_start(c.lessons_on(dt_util.now().date())),
    ),
    ChildSensorDescription(
        key="school_end_today",
        translation_key="school_end_today",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: _last_end(c.lessons_on(dt_util.now().date())),
    ),
    ChildSensorDescription(
        key="next_school_day_start",
        translation_key="next_school_day_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda c: _first_start(_next_school_day(c)),
        attrs_fn=lambda c: {
            "end": (e.isoformat() if (e := _last_end(_next_school_day(c))) else None),
            "lessons": [les.subject for les in _next_school_day(c)],
        },
    ),
    ChildSensorDescription(
        key="absences",
        translation_key="absences",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda c: None if c.absences is None else len(c.absences),
        attrs_fn=lambda c: {
            "summary": c.absence_summary,
            "latest": (c.absences or [])[-10:],
        },
    ),
    ChildSensorDescription(
        key="sfo_today",
        translation_key="sfo_today",
        device_class=SensorDeviceClass.ENUM,
        options=["til_stede", "sjekket_ut", "ikke_registrert", "ingen_sfo_i_dag"],
        value_fn=_sfo_state,
        attrs_fn=lambda c: {"details": c.sfo_today},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlytConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [UnansweredFormsSensor(coordinator)]
    for child_key in coordinator.data.children:
        entities.extend(
            FlytChildSensor(coordinator, child_key, desc) for desc in CHILD_SENSORS
        )
    async_add_entities(entities)


class FlytChildSensor(FlytChildEntity, SensorEntity):
    """A sensor for one child."""

    entity_description: ChildSensorDescription

    def __init__(
        self,
        coordinator: FlytCoordinator,
        child_key: str,
        description: ChildSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, child_key, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the state."""
        child = self.child
        return self.entity_description.value_fn(child) if child else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        child = self.child
        if child is None or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(child)


class UnansweredFormsSensor(FlytAccountEntity, SensorEntity):
    """Number of unanswered digital forms / consents."""

    _attr_translation_key = "unanswered_forms"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: FlytCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "unanswered_forms")

    @property
    def native_value(self) -> int | None:
        """Return the state."""
        return self.coordinator.data.unanswered_forms
