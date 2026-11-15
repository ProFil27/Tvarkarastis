"""Reminders to upload an updated timetable at the start of a semester or month (F-20, F-21, PK-1..PK-3).

Reminders are shown only inside the system (N-47): no e-mails or other external messages.
"""

from datetime import date
from typing import Callable

from app.application.ports import ReminderSettingRepository, ScheduleRepository
from app.domain.clock import local_today
from app.domain.entities import Reminder
from app.domain.reminder import SemesterStarts, current_period, in_reminder_window

REMINDER_TEXT = "Prasidėjo naujas laikotarpis. Įkelkite atnaujintą tvarkaraštį."


class ReminderService:
    def __init__(
        self,
        settings: ReminderSettingRepository,
        schedules: ScheduleRepository,
        semester_starts: SemesterStarts,
        today: Callable[[], date] = local_today,
    ):
        self._settings = settings
        self._schedules = schedules
        self._semester_starts = semester_starts
        self._today = today

    def get_active_reminder(self, user_id: int) -> Reminder | None:
        """The reminder to show now, or None.

        Shown when reminders are enabled, it is one of the first 7 days of the period, no schedule was
        uploaded since the period began and the user has not closed this period's reminder.
        """
        setting = self._settings.get(user_id)
        if not setting.enabled:
            return None
        today = self._today()
        period_start, reminder_type = current_period(today, self._semester_starts)
        if not in_reminder_window(today, period_start) or setting.closed_period_start == period_start:
            return None
        last_upload = self._schedules.last_schedule_date(user_id)
        if last_upload is not None and last_upload >= period_start:
            return None
        return Reminder(period_start, reminder_type, REMINDER_TEXT)

    def close(self, user_id: int) -> None:
        """Hide the reminder until the next period (F-21)."""
        period_start, reminder_type = current_period(self._today(), self._semester_starts)
        self._settings.set_closed_period(user_id, period_start, reminder_type)

    def disable(self, user_id: int) -> None:
        self._settings.set_enabled(user_id, False)

    def enable(self, user_id: int) -> None:
        self._settings.set_enabled(user_id, True)

    def is_enabled(self, user_id: int) -> bool:
        return self._settings.get(user_id).enabled
