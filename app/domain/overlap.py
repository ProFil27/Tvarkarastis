"""Domain rule for time conflicts (N-09)."""

from datetime import time

from app.domain.entities import StudyEvent, WorkShift


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def overlap_minutes(event: StudyEvent, shift: WorkShift) -> int:
    """Overlap of a study event and a work shift in minutes.

    Returns 0 when they fall on different weekdays or only touch (one ends exactly
    when the other starts); touching intervals are not conflicts.
    """
    if event.weekday != shift.weekday:
        return 0
    start = max(_minutes(event.start_time), _minutes(shift.start_time))
    end = min(_minutes(event.end_time), _minutes(shift.end_time))
    return max(0, end - start)
