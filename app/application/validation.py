"""Small validation helpers shared by services."""

from datetime import datetime, time
from typing import Callable

TIME_FORMAT = "%H:%M"


def parse_time(value: str | None) -> time | None:
    """Parse "HH:MM" (24h); None if the value is missing or malformed."""
    try:
        return datetime.strptime(value or "", TIME_FORMAT).time()
    except ValueError:
        return None


def format_time(value: time) -> str:
    return value.strftime(TIME_FORMAT)


def validate_time_range(start: str | None, end: str | None) -> dict[str, str]:
    """Validate a start/end pair. Returns {field: code}; empty if valid."""
    errors: dict[str, str] = {}
    start_time = parse_time(start)
    end_time = parse_time(end)
    if start_time is None:
        errors["start_time"] = "invalid_time"
    if end_time is None:
        errors["end_time"] = "invalid_time"
    if start_time is not None and end_time is not None and end_time <= start_time:
        errors["end_time"] = "end_not_after_start"
    return errors


# Hook called with a user id after that user's schedule or shifts change (F-12).
ChangeListener = Callable[[int], None]


def ignore_changes(user_id: int) -> None:
    """Default listener that does nothing."""
