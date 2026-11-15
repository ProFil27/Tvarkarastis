"""Domain rule for time conflicts (N-09)."""

from datetime import time

from app.domain.academic_week import pattern_applies
from app.domain.entities import StudyEvent, WorkShift


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def overlap_minutes(event: StudyEvent, shift: WorkShift) -> int:
    """Overlap of a study event and a work shift in minutes.

    Study events repeat weekly while their schedule is valid; a work shift happens on one date.
    Returns 0 when the shift falls on another weekday, outside the schedule's validity or in a study week
    (1 / 2) in which the event does not take place, or when
    the intervals only touch (one ends exactly when the other starts) - touching is not a conflict.
    """
    if event.weekday != shift.weekday:
        return 0
    if event.valid_from is not None and shift.work_date < event.valid_from:
        return 0
    if event.valid_to is not None and shift.work_date > event.valid_to:
        return 0
    if not pattern_applies(event.week_pattern, shift.work_date):
        return 0
    start = max(_minutes(event.start_time), _minutes(shift.start_time))
    end = min(_minutes(event.end_time), _minutes(shift.end_time))
    return max(0, end - start)
