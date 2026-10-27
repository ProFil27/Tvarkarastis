from app.application.errors import ValidationFailed
from app.application.ports import WorkShiftRepository
from app.application.validation import ChangeListener, ignore_changes, parse_time, validate_time_range
from app.domain.entities import WorkShift
from app.domain.weekday import Weekday

class WorkShiftService:
    def __init__(self, shifts: WorkShiftRepository, on_change: ChangeListener = ignore_changes):
        self._shifts = shifts
        self._on_change = on_change

    def add_shift(
        self, user_id: int, workplace_name: str, weekday: Weekday | None, start: str, end: str
    ) -> WorkShift:
        errors = validate_time_range(start, end)
        if not workplace_name or not workplace_name.strip():
            errors["workplace_name"] = "required"
        if weekday is None:
            errors["weekday"] = "invalid_choice"
        if errors:
            raise ValidationFailed(errors)

        shift = self._shifts.add(user_id, workplace_name.strip(), weekday, parse_time(start), parse_time(end))
        self._on_change(user_id)
        return shift

    def list_shifts(self, user_id: int) -> list[WorkShift]:
        return self._shifts.list_for_user(user_id)

    def remove_shift(self, user_id: int, shift_id: int) -> bool:
        removed = self._shifts.remove(user_id, shift_id)
        if removed:
            self._on_change(user_id)
        return removed
