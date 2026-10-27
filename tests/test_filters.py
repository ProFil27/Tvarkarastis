from datetime import time

import pytest

from app.application.week_view_service import ConflictDetail
from app.domain.entities import StudyEvent, StudyEventType, WorkShift
from app.domain.weekday import Weekday
from app.web.filters import initials, plural_lt, timeline


@pytest.mark.parametrize("name,expected", [("Edvinas Rudys", "ER"), ("jonas", "J"), ("a b c", "AB"), ("", "?"), (None, "?")])
def test_initials(name, expected):
    assert initials(name) == expected


@pytest.mark.parametrize(
    "count,expected",
    [(0, "pamainų"), (1, "pamaina"), (2, "pamainos"), (9, "pamainos"), (10, "pamainų"), (11, "pamainų"), (21, "pamaina"), (22, "pamainos")],
)
def test_lithuanian_plural(count, expected):
    assert plural_lt(count, "pamaina", "pamainos", "pamainų") == expected


def test_overlap_bar_scale_matches_the_mockup_example():
    event = StudyEvent(1, "Duomenų bazės", StudyEventType.LECTURE, Weekday.MONDAY, time(8, 30), time(10, 0), None)
    shift = WorkShift(1, "UAB Pavyzdys", Weekday.MONDAY, time(9, 0), time(13, 0))
    bar = timeline(ConflictDetail(event, shift, 60))
    assert bar["event_left"] == 0 and bar["overlap_width"] == round(60 * 100 / 270, 1)
    assert bar["shift_left"] == round(30 * 100 / 270, 1) and bar["shift_width"] == round(240 * 100 / 270, 1)
