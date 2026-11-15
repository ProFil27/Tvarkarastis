"""Manual editing of study events: add, change, remove (F-17, TVK-9, TVK-10, TVK-11)."""

from datetime import date, timedelta
from typing import Callable

from app.application.errors import ValidationFailed
from app.application.event_rows import ReviewRow, row_to_event, validate_row
from app.application.ports import ScheduleRepository
from app.application.validation import ChangeListener, ignore_changes
from app.domain.clock import local_today
from app.domain.entities import StudyEvent
from app.domain.rules import SEMESTER_LENGTH_DAYS


class StudyEventService:
    def __init__(
        self,
        schedules: ScheduleRepository,
        on_change: ChangeListener = ignore_changes,
        today: Callable[[], date] = local_today,
    ):
        self._schedules = schedules
        self._on_change = on_change
        self._today = today

    def list_events(self, user_id: int) -> list[StudyEvent]:
        """The user's events ordered by weekday, then start time."""
        events = self._schedules.list_study_events(user_id)
        return sorted(events, key=lambda e: (e.weekday.index, e.start_time, e.subject_name))

    def get_event(self, user_id: int, event_id: int) -> StudyEvent | None:
        return self._schedules.get_event(user_id, event_id)

    def add_event(self, user_id: int, row: ReviewRow) -> StudyEvent:
        """Raises ValidationFailed with {field: code}."""
        self._validate(row)
        today = self._today()
        event = self._schedules.add_event(
            user_id, row_to_event(row), today, today + timedelta(days=SEMESTER_LENGTH_DAYS)
        )
        self._on_change(user_id)
        return event

    def update_event(self, user_id: int, event_id: int, row: ReviewRow) -> StudyEvent | None:
        """Change all fields of the user's event; None if it does not exist or is not theirs."""
        self._validate(row)
        event = self._schedules.update_event(user_id, event_id, row_to_event(row))
        if event is not None:
            self._on_change(user_id)
        return event

    def remove_event(self, user_id: int, event_id: int) -> bool:
        removed = self._schedules.remove_event(user_id, event_id)
        if removed:
            self._on_change(user_id)
        return removed

    @staticmethod
    def _validate(row: ReviewRow) -> None:
        errors = validate_row(row)
        if errors:
            raise ValidationFailed(errors)
