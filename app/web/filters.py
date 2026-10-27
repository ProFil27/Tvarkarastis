"""Jinja helpers for presentation only."""

from app.application.week_view_service import ConflictDetail
from app.domain.entities import StudyEventType

_EVENT_TYPE_LABELS = {
    StudyEventType.LECTURE: "paskaita",
    StudyEventType.PRACTICAL: "pratybos",
    StudyEventType.LABORATORY: "laboratorinis darbas",
}


def initials(name: str | None) -> str:
    """Up to two capital letters for the avatar."""
    letters = "".join(part[0] for part in (name or "").split()[:2])
    return (letters or "?").upper()


def plural_lt(count: int, one: str, few: str, many: str) -> str:
    """Pick the Lithuanian plural form for `count` (1 / 2-9 / 0, 10-20 and tens)."""
    last_two, last = count % 100, count % 10
    if last == 1 and last_two != 11:
        return one
    if 2 <= last <= 9 and not 11 <= last_two <= 19:
        return few
    return many


def event_type_label(event_type: StudyEventType) -> str:
    return _EVENT_TYPE_LABELS[event_type]


def _minutes(value) -> int:
    return value.hour * 60 + value.minute


def timeline(detail: ConflictDetail) -> dict[str, float]:
    """Percent offsets/widths for the overlap bar: study event, overlap and work shift on one scale."""
    event, shift = detail.event, detail.shift
    start = min(_minutes(event.start_time), _minutes(shift.start_time))
    end = max(_minutes(event.end_time), _minutes(shift.end_time))
    span = max(end - start, 1)
    overlap_start = max(_minutes(event.start_time), _minutes(shift.start_time))
    overlap_end = min(_minutes(event.end_time), _minutes(shift.end_time))

    def pct(value: int) -> float:
        return round(value * 100 / span, 1)

    return {
        "event_left": pct(_minutes(event.start_time) - start),
        "event_width": pct(_minutes(event.end_time) - _minutes(event.start_time)),
        "shift_left": pct(_minutes(shift.start_time) - start),
        "shift_width": pct(_minutes(shift.end_time) - _minutes(shift.start_time)),
        "overlap_left": pct(overlap_start - start),
        "overlap_width": pct(overlap_end - overlap_start),
    }
