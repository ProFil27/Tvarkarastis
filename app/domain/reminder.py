"""When a reminder to upload an updated timetable is due (F-20).

A period starts on a semester start date or on the 1st of a month, whichever came last. The reminder is
due during the first REMINDER_WINDOW_DAYS calendar days of the period.
"""

from datetime import date

from app.domain.entities import ReminderType
from app.domain.rules import REMINDER_WINDOW_DAYS

# (month, day) pairs, e.g. [(9, 1), (2, 1)]
SemesterStarts = list[tuple[int, int]]


def current_period(today: date, semester_starts: SemesterStarts) -> tuple[date, ReminderType]:
    """Start of the latest period that has begun and its type; a semester start wins over a month start."""
    month_start = today.replace(day=1)
    semester_dates = [
        date(year, month, day)
        for year in (today.year - 1, today.year)
        for month, day in semester_starts
        if date(year, month, day) <= today
    ]
    latest_semester = max(semester_dates, default=None)
    if latest_semester is not None and latest_semester >= month_start:
        return latest_semester, ReminderType.SEMESTER_START
    return month_start, ReminderType.MONTH_START


def in_reminder_window(today: date, period_start: date) -> bool:
    """First REMINDER_WINDOW_DAYS calendar days of the period, counting the start day."""
    return 0 <= (today - period_start).days < REMINDER_WINDOW_DAYS
