"""Weekly schedule view and notifications (F-11, F-15, F-16).

The week view is computed on the fly and is not stored (TimeInterval class).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.application.ports import (
    ConflictRepository,
    NotificationRepository,
    ScheduleRepository,
    WorkShiftRepository,
)
from app.domain.entities import Notification, StudyEvent, WorkShift
from app.domain.weekday import Weekday


@dataclass(frozen=True)
class WeekEvent:
    event: StudyEvent
    has_conflict: bool


@dataclass(frozen=True)
class WeekShift:
    shift: WorkShift
    has_conflict: bool


@dataclass(frozen=True)
class ConflictDetail:
    event: StudyEvent
    shift: WorkShift
    overlap_minutes: int


@dataclass(frozen=True)
class DayView:
    weekday: Weekday
    date: date
    events: list[WeekEvent] = field(default_factory=list)
    shifts: list[WeekShift] = field(default_factory=list)
    conflicts: list[ConflictDetail] = field(default_factory=list)

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)


@dataclass(frozen=True)
class WeekView:
    week_start: date
    week_end: date
    previous_week: date
    next_week: date
    days: list[DayView]
    has_data: bool


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


class WeekViewService:
    def __init__(
        self,
        schedules: ScheduleRepository,
        shifts: WorkShiftRepository,
        conflicts: ConflictRepository,
        notifications: NotificationRepository,
    ):
        self._schedules = schedules
        self._shifts = shifts
        self._conflicts = conflicts
        self._notifications = notifications

    def get_week(self, user_id: int, week_start: date) -> WeekView:
        week_start = monday_of(week_start)
        week_end = week_start + timedelta(days=6)

        events = self._schedules.list_study_events(user_id, week_start, week_end)
        shifts = self._shifts.list_for_user(user_id)
        events_by_id = {e.id: e for e in events}
        shifts_by_id = {s.id: s for s in shifts}
        conflicts = [
            c
            for c in self._conflicts.list_active(user_id)
            if c.study_event_id in events_by_id and c.work_shift_id in shifts_by_id
        ]
        conflicted_events = {c.study_event_id for c in conflicts}
        conflicted_shifts = {c.work_shift_id for c in conflicts}

        days = []
        for weekday in Weekday:
            days.append(
                DayView(
                    weekday=weekday,
                    date=week_start + timedelta(days=weekday.index),
                    events=[WeekEvent(e, e.id in conflicted_events) for e in events if e.weekday == weekday],
                    shifts=[WeekShift(s, s.id in conflicted_shifts) for s in shifts if s.weekday == weekday],
                    conflicts=[
                        ConflictDetail(events_by_id[c.study_event_id], shifts_by_id[c.work_shift_id], c.overlap_minutes)
                        for c in conflicts
                        if events_by_id[c.study_event_id].weekday == weekday
                    ],
                )
            )

        return WeekView(
            week_start=week_start,
            week_end=week_end,
            previous_week=week_start - timedelta(days=7),
            next_week=week_start + timedelta(days=7),
            days=days,
            has_data=bool(events or shifts),
        )

    def unread_notifications(self, user_id: int) -> list[Notification]:
        return self._notifications.list_unread(user_id)

    def dismiss_notification(self, user_id: int, notification_id: int) -> bool:
        return self._notifications.mark_read(user_id, notification_id)
