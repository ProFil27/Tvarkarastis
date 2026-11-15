"""Alternating study weeks (week 1 / week 2).

Some lectures take place only on week 1 or only on week 2. The academic year starts in September:
week 1 is the Monday-Sunday week that contains 1 September, and the weeks then alternate 1, 2, 1, 2 ...
without restarting in the spring semester.
"""

from datetime import date, timedelta

from app.domain.entities import WeekPattern


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def academic_anchor(day: date) -> date:
    """Monday of week 1 of the academic year that `day` belongs to."""
    anchor = _monday(date(day.year, 9, 1))
    return anchor if day >= anchor else _monday(date(day.year - 1, 9, 1))


def week_number(day: date) -> int:
    """1 or 2: the study week `day` falls in."""
    weeks_since_start = (_monday(day) - academic_anchor(day)).days // 7
    return 1 if weeks_since_start % 2 == 0 else 2


def pattern_applies(pattern: WeekPattern, day: date) -> bool:
    """Whether an event with this week pattern takes place in the week of `day`."""
    if pattern == WeekPattern.EVERY_WEEK:
        return True
    return week_number(day) == (1 if pattern == WeekPattern.WEEK_1 else 2)
