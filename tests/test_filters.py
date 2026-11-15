from datetime import date, time

import pytest

from app.application.week_view_service import ConflictDetail
from app.domain.entities import StudyEvent, StudyEventType, WorkShift
from app.domain.weekday import Weekday
from app.web.filters import initials, plural_lt, timeline


@pytest.mark.parametrize(
    "name,expected", [("Edvinas Rudys", "ER"), ("jonas", "J"), ("a b c", "AB"), ("", "?"), (None, "?")]
)
def test_initials(name, expected):
    assert initials(name) == expected


@pytest.mark.parametrize(
    "count,expected",
    [
        (0, "pamainų"), (1, "pamaina"), (2, "pamainos"), (9, "pamainos"),
        (10, "pamainų"), (11, "pamainų"), (21, "pamaina"), (22, "pamainos"),
    ],
)
def test_lithuanian_plural(count, expected):
    assert plural_lt(count, "pamaina", "pamainos", "pamainų") == expected


def test_overlap_bar_scale_matches_the_mockup_example():
    event = StudyEvent(1, "Duomenų bazės", StudyEventType.LECTURE, Weekday.MONDAY, time(8, 30), time(10, 0), None)
    shift = WorkShift(1, "UAB Pavyzdys", date(2026, 10, 26), time(9, 0), time(13, 0))
    bar = timeline(ConflictDetail(event, shift, 60))
    assert bar["event_left"] == 0 and bar["overlap_width"] == round(60 * 100 / 270, 1)
    assert bar["shift_left"] == round(30 * 100 / 270, 1) and bar["shift_width"] == round(240 * 100 / 270, 1)


def test_time_fields_are_text_inputs_with_the_shared_script_instead_of_the_native_picker():
    from app.application.work_shift_service import WorkShiftService
    from app.container import Services
    from app.web import create_app
    from tests import fakes

    client = create_app(services=Services(work_shifts=WorkShiftService(fakes.FakeWorkShiftRepository()))).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1

    page = client.get("/work-shifts/").get_data(as_text=True)
    assert page.count("data-time-input") == 2 and 'type="time"' not in page
    assert "js/time_field.js" in page
    assert 'placeholder="HH:MM"' in page and 'pattern="([01][0-9]|2[0-3]):[0-5][0-9]"' in page

    invalid = client.post(
        "/work-shifts/add", data={"workplace_name": "K", "work_date": "2026-10-26", "start_time": "18:00", "end_time": "10:00"}
    ).get_data(as_text=True)
    assert 'aria-invalid="true"' in invalid and 'value="18:00"' in invalid
