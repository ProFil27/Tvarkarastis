import pytest

from app.application.errors import ValidationFailed
from app.application.work_shift_service import WorkShiftService
from app.container import Services
from app.domain.weekday import Weekday
from app.web import create_app
from tests import fakes

SHIFT_FORM = {"workplace_name": "Kavine", "work_date": "2026-10-26", "start_time": "10:00", "end_time": "14:00"}


def test_validation_codes_and_change_listener():
    changed = []
    service = WorkShiftService(fakes.FakeWorkShiftRepository(), on_change=changed.append)

    with pytest.raises(ValidationFailed) as exc:
        service.add_shift(1, "", "2026-13-40", "18:00", "10:00")
    assert exc.value.errors == {
        "workplace_name": "required",
        "work_date": "invalid_date",
        "end_time": "end_not_after_start",
    }

    shift = service.add_shift(1, "Kavine", "2026-10-26", "15:00", "19:00")
    assert service.list_shifts(1) == [shift]
    assert shift.work_date.isoformat() == "2026-10-26" and shift.weekday == Weekday.MONDAY
    assert changed == [1]

    assert service.remove_shift(2, shift.id) is False  # another user's shift (N-21)
    assert service.remove_shift(1, shift.id) is True
    assert changed == [1, 1]


def logged_in_client(service, user_id=1):
    client = create_app(services=Services(work_shifts=service)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def test_shift_form_shows_lithuanian_errors_and_saves_valid_shift():
    client = logged_in_client(WorkShiftService(fakes.FakeWorkShiftRepository()))

    invalid = client.post("/work-shifts/add", data={**SHIFT_FORM, "start_time": "18:00"})
    assert "vėlesnis už pradžios laiką" in invalid.get_data(as_text=True)

    assert client.post("/work-shifts/add", data=SHIFT_FORM).status_code == 302
    assert "Kavine" in client.get("/work-shifts/").get_data(as_text=True)


def test_user_cannot_remove_another_users_shift_over_http():
    service = WorkShiftService(fakes.FakeWorkShiftRepository())
    owner = logged_in_client(service, user_id=1)
    owner.post("/work-shifts/add", data=SHIFT_FORM)

    other = logged_in_client(service, user_id=2)
    other.post("/work-shifts/1/remove")

    assert "Kavine" in owner.get("/work-shifts/").get_data(as_text=True)


def test_update_changes_the_shift_validates_and_notifies():
    changed = []
    service = WorkShiftService(fakes.FakeWorkShiftRepository(), on_change=changed.append)
    shift = service.add_shift(1, "Kavine", "2026-10-26", "10:00", "14:00")

    updated = service.update_shift(1, shift.id, "UAB Pavyzdys", "2026-10-28", "12:30", "16:00")

    assert (updated.workplace_name, updated.work_date.isoformat(), updated.start_time.hour, updated.end_time.hour) == (
        "UAB Pavyzdys", "2026-10-28", 12, 16)
    assert service.get_shift(1, shift.id) == updated and updated.updated_at >= shift.updated_at
    assert changed == [1, 1]

    with pytest.raises(ValidationFailed) as exc:
        service.update_shift(1, shift.id, "x" * 101, "nope", "18:00", "10:00")
    assert exc.value.errors == {
        "workplace_name": "too_long", "work_date": "invalid_date", "end_time": "end_not_after_start",
    }
    assert service.get_shift(1, shift.id) == updated and changed == [1, 1]  # invalid edit changes nothing


def test_a_user_cannot_read_or_change_another_users_shift():
    changed = []
    service = WorkShiftService(fakes.FakeWorkShiftRepository(), on_change=changed.append)
    shift = service.add_shift(1, "Kavine", "2026-10-26", "10:00", "14:00")
    changed.clear()

    assert service.get_shift(2, shift.id) is None
    assert service.update_shift(2, shift.id, "Kita", "2026-10-26", "10:00", "14:00") is None
    assert changed == [] and service.get_shift(1, shift.id).workplace_name == "Kavine"


def test_edit_flow_over_http_shows_the_form_filled_and_saves_the_change():
    service = WorkShiftService(fakes.FakeWorkShiftRepository())
    client = logged_in_client(service)
    client.post("/work-shifts/add", data=SHIFT_FORM)

    page = client.get("/work-shifts/1/edit").get_data(as_text=True)
    assert "Keisti pamainą" in page and 'value="Kavine"' in page and 'value="2026-10-26"' in page
    assert 'value="10:00"' in page and ">Keisti</a>" in page

    invalid = client.post("/work-shifts/1/edit", data={**SHIFT_FORM, "start_time": "18:00"})
    assert "vėlesnis už pradžios laiką" in invalid.get_data(as_text=True)

    assert client.post("/work-shifts/1/edit", data={**SHIFT_FORM, "workplace_name": "Naujas darbas"}).status_code == 302
    listing = client.get("/work-shifts/").get_data(as_text=True)
    assert "Naujas darbas" in listing and "Kavine" not in listing


def test_user_cannot_edit_another_users_shift_over_http():
    service = WorkShiftService(fakes.FakeWorkShiftRepository())
    owner = logged_in_client(service, user_id=1)
    owner.post("/work-shifts/add", data=SHIFT_FORM)

    other = logged_in_client(service, user_id=2)
    assert other.get("/work-shifts/1/edit").status_code == 302
    other.post("/work-shifts/1/edit", data={**SHIFT_FORM, "workplace_name": "Hacked"})

    assert "Kavine" in owner.get("/work-shifts/").get_data(as_text=True)


def test_weekly_repeat_creates_the_same_weekday_every_week_up_to_the_end_date_inclusive():
    changed = []
    service = WorkShiftService(fakes.FakeWorkShiftRepository(), on_change=changed.append)

    shifts = service.add_weekly_shifts(1, "Kavine", "2026-10-28", "10:00", "14:00", "2026-11-18")  # Wednesdays

    assert [s.work_date.isoformat() for s in shifts] == ["2026-10-28", "2026-11-04", "2026-11-11", "2026-11-18"]
    assert {s.weekday for s in shifts} == {Weekday.WEDNESDAY} and len(service.list_shifts(1)) == 4
    assert changed == [1]  # the conflict search / calendar update run once, not once per shift


def test_weekly_repeat_stops_before_an_end_date_that_is_not_the_same_weekday():
    service = WorkShiftService(fakes.FakeWorkShiftRepository())
    shifts = service.add_weekly_shifts(1, "Kavine", "2026-10-28", "10:00", "14:00", "2026-11-17")
    assert [s.work_date.isoformat() for s in shifts] == ["2026-10-28", "2026-11-04", "2026-11-11"]


@pytest.mark.parametrize(
    "until,code", [("nope", "invalid_date"), ("2026-10-21", "before_start"), ("2030-01-01", "too_many")]
)
def test_weekly_repeat_validation_creates_nothing(until, code):
    changed = []
    service = WorkShiftService(fakes.FakeWorkShiftRepository(), on_change=changed.append)

    with pytest.raises(ValidationFailed) as exc:
        service.add_weekly_shifts(1, "Kavine", "2026-10-28", "10:00", "14:00", until)

    assert exc.value.errors == {"repeat_until": code} and service.list_shifts(1) == [] and changed == []


def test_repeat_field_over_http_adds_all_weeks_and_shows_errors():
    client = logged_in_client(WorkShiftService(fakes.FakeWorkShiftRepository()))

    assert "Kartoti kas savaitę iki" in client.get("/work-shifts/").get_data(as_text=True)
    bad = client.post("/work-shifts/add", data={**SHIFT_FORM, "repeat_until": "2026-10-01"})
    assert "Kartojimo pabaiga negali būti ankstesnė" in bad.get_data(as_text=True)

    client.post("/work-shifts/add", data={**SHIFT_FORM, "repeat_until": "2026-11-16"})  # 26 Oct is a Monday
    page = client.get("/work-shifts/").get_data(as_text=True)
    assert page.count("2026-11-09") >= 1 and "2026-11-16" in page
