from datetime import timedelta

from app.application.errors import ValidationFailed
from app.application.ports import ShiftSeriesRepository, WorkShiftRepository
from app.application.validation import ChangeListener, ignore_changes, parse_date, parse_time, validate_time_range
from app.domain.entities import ShiftSeries, WorkShift
from app.domain.rules import MAX_SHIFT_REPEATS, MAX_WORKPLACE_LENGTH


class WorkShiftService:
    def __init__(
        self,
        shifts: WorkShiftRepository,
        on_change: ChangeListener = ignore_changes,
        series: ShiftSeriesRepository | None = None,
    ):
        self._shifts = shifts
        self._on_change = on_change
        self._series = series

    def add_shift(self, user_id: int, workplace_name: str, work_date: str, start: str, end: str) -> WorkShift:
        self._validate(workplace_name, work_date, start, end)
        shift = self._shifts.add(
            user_id, workplace_name.strip(), parse_date(work_date), parse_time(start), parse_time(end)
        )
        self._on_change(user_id)
        return shift

    def add_weekly_shifts(
        self, user_id: int, workplace_name: str, work_date: str, start: str, end: str, repeat_until: str
    ) -> list[WorkShift]:
        """Add the shift on `work_date` and on the same weekday of every following week up to `repeat_until`
        (inclusive) as one series: it is edited, removed and exported to the calendar as a whole.
        """
        self._validate(workplace_name, work_date, start, end)
        first = parse_date(work_date)
        days = self._series_dates(first, repeat_until)

        if len(days) == 1:  # nothing repeats: an ordinary shift
            shifts = [self._shifts.add(user_id, workplace_name.strip(), first, parse_time(start), parse_time(end))]
        else:
            shifts = self._series.create(user_id, workplace_name.strip(), parse_time(start), parse_time(end), days)
        self._on_change(user_id)
        return shifts

    def get_series(self, user_id: int, series_id: int) -> ShiftSeries | None:
        return self._series.get(user_id, series_id)

    def update_series(
        self, user_id: int, series_id: int, workplace_name: str, start: str, end: str, repeat_until: str
    ) -> ShiftSeries | None:
        """Change a whole series: workplace, times and the last day. Shifts that were changed on their own
        (exceptions) keep their values. None if the series does not exist or is not the user's.
        """
        errors = validate_time_range(start, end)
        self._check_workplace(workplace_name, errors)
        if errors:
            raise ValidationFailed(errors)
        series = self._series.get(user_id, series_id)
        if series is None:
            return None

        days = self._series_dates(series.first_date, repeat_until)
        new_dates = [day for day in days if day > series.last_date]
        updated = self._series.update(
            user_id, series_id, workplace_name.strip(), parse_time(start), parse_time(end), days[-1], new_dates
        )
        if updated is not None:
            self._on_change(user_id)
        return updated

    def remove_series(self, user_id: int, series_id: int) -> bool:
        removed = self._series.remove(user_id, series_id)
        if removed:
            self._on_change(user_id)
        return removed

    @staticmethod
    def _series_dates(first, repeat_until: str) -> list:
        """The weekly dates from `first` to `repeat_until`, inclusive. Raises ValidationFailed."""
        last = parse_date(repeat_until)
        if last is None:
            raise ValidationFailed({"repeat_until": "invalid_date"})
        if last < first:
            raise ValidationFailed({"repeat_until": "before_start"})
        days = [first + timedelta(weeks=n) for n in range((last - first).days // 7 + 1)]
        if len(days) > MAX_SHIFT_REPEATS:
            raise ValidationFailed({"repeat_until": "too_many"})
        return days

    def update_shift(
        self, user_id: int, shift_id: int, workplace_name: str, work_date: str, start: str, end: str
    ) -> WorkShift | None:
        """Change the user's shift (F-18); None if it does not exist or is not theirs."""
        self._validate(workplace_name, work_date, start, end)
        shift = self._shifts.update(
            user_id, shift_id, workplace_name.strip(), parse_date(work_date), parse_time(start), parse_time(end)
        )
        if shift is not None:
            self._on_change(user_id)
        return shift

    def get_shift(self, user_id: int, shift_id: int) -> WorkShift | None:
        return self._shifts.get(user_id, shift_id)

    def list_shifts(self, user_id: int) -> list[WorkShift]:
        return self._shifts.list_for_user(user_id)

    def remove_shift(self, user_id: int, shift_id: int) -> bool:
        removed = self._shifts.remove(user_id, shift_id)
        if removed:
            self._on_change(user_id)
        return removed

    @staticmethod
    def _check_workplace(workplace_name: str, errors: dict) -> None:
        if not workplace_name or not workplace_name.strip():
            errors["workplace_name"] = "required"
        elif len(workplace_name.strip()) > MAX_WORKPLACE_LENGTH:
            errors["workplace_name"] = "too_long"

    @classmethod
    def _validate(cls, workplace_name: str, work_date: str, start: str, end: str) -> None:
        errors = validate_time_range(start, end)
        cls._check_workplace(workplace_name, errors)
        if parse_date(work_date) is None:
            errors["work_date"] = "invalid_date"
        if errors:
            raise ValidationFailed(errors)
