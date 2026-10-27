import pytest

from app.application.errors import ValidationFailed
from app.application.work_shift_service import WorkShiftService
from app.container import Services
from app.domain.weekday import Weekday
from app.web import create_app
from tests import fakes

SHIFT_FORM = {"workplace_name": "Kavine", "day_of_week": "Pirmadienis", "start_time": "10:00", "end_time": "14:00"}


def test_validation_codes_and_change_listener():
    changed = []
    service = WorkShiftService(fakes.FakeWorkShiftRepository(), on_change=changed.append)

    with pytest.raises(ValidationFailed) as exc:
        service.add_shift(1, "", None, "18:00", "10:00")
    assert exc.value.errors == {
        "workplace_name": "required",
        "weekday": "invalid_choice",
        "end_time": "end_not_after_start",
    }

    shift = service.add_shift(1, "Kavine", Weekday.MONDAY, "15:00", "19:00")
    assert service.list_shifts(1) == [shift]
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
