"""Form rows describing one study event, shared by the review table and the lecture editor (F-06, F-17)."""

from dataclasses import asdict, dataclass

from app.application.validation import format_time, parse_time, validate_time_range
from app.domain.entities import StudyEvent, StudyEventType, WeekPattern
from app.domain.rules import MAX_ROOM_LENGTH, MAX_SUBJECT_LENGTH
from app.domain.weekday import Weekday


@dataclass(frozen=True)
class ReviewRow:
    """One editable row (review table or lecture form). All values are raw form strings."""

    subject: str
    event_type: str
    day_of_week: str
    start_time: str
    end_time: str
    room: str
    is_mandatory: bool
    week_pattern: str = WeekPattern.EVERY_WEEK.value

    @classmethod
    def from_event(cls, event: StudyEvent) -> "ReviewRow":
        return cls(
            subject=event.subject_name,
            event_type=event.event_type.value,
            day_of_week=event.weekday.value,
            start_time=format_time(event.start_time),
            end_time=format_time(event.end_time),
            room=event.room or "",
            is_mandatory=event.is_mandatory,
            week_pattern=event.week_pattern.value,
        )

    def to_dict(self) -> dict:
        return asdict(self)


def validate_row(row: ReviewRow) -> dict[str, str]:
    """{field: error_code} for one row; an empty dict means the row is valid."""
    errors = validate_time_range(row.start_time, row.end_time)
    if not row.subject or not row.subject.strip():
        errors["subject"] = "required"
    elif len(row.subject.strip()) > MAX_SUBJECT_LENGTH:
        errors["subject"] = "too_long"
    if row.event_type not in {t.value for t in StudyEventType}:
        errors["event_type"] = "invalid_choice"
    if Weekday.from_code(row.day_of_week) is None:
        errors["day_of_week"] = "invalid_choice"
    if row.week_pattern not in {p.value for p in WeekPattern}:
        errors["week_pattern"] = "invalid_choice"
    if len(row.room.strip()) > MAX_ROOM_LENGTH:
        errors["room"] = "too_long"
    return errors


def row_to_event(row: ReviewRow) -> StudyEvent:
    """Build the (unsaved) study event from a row that passed `validate_row`."""
    return StudyEvent(
        id=None,
        subject_name=row.subject.strip(),
        event_type=StudyEventType(row.event_type),
        weekday=Weekday(row.day_of_week),
        start_time=parse_time(row.start_time),
        end_time=parse_time(row.end_time),
        room=row.room.strip() or None,
        is_mandatory=row.is_mandatory,
        week_pattern=WeekPattern(row.week_pattern),
    )
