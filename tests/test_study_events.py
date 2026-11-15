"""Manual editing of study events (F-17, US-08)."""

from datetime import date, time

import pytest

from app.application.errors import ValidationFailed
from app.application.event_rows import ReviewRow
from app.application.study_event_service import StudyEventService
from app.container import Services
from app.domain.entities import WeekPattern
from app.web import create_app
from tests import fakes

ROW = ReviewRow("Duomenų bazės", "PASKAITA", "ANTRADIENIS", "10:00", "11:30", "SRK-I-101", True)
FORM = {
    "subject": "Duomenų bazės", "event_type": "PASKAITA", "day_of_week": "ANTRADIENIS", "week_pattern": "KIEKVIENA",
    "start_time": "10:00", "end_time": "11:30", "room": "SRK-I-101", "is_mandatory": "on",
}


def make_service(changed=None):
    schedules = fakes.FakeScheduleRepository()
    listener = changed.append if changed is not None else (lambda user_id: None)
    return StudyEventService(schedules, listener, today=lambda: date(2026, 11, 14)), schedules


def test_add_stores_the_event_in_a_default_schedule_and_notifies_listeners():
    changed = []
    service, schedules = make_service(changed)

    event = service.add_event(1, ROW)

    assert event.subject_name == "Duomenų bazės" and event.start_time == time(10, 0) and event.updated_at
    assert schedules.saved_schedules == [{"user_id": 1, "valid_from": date(2026, 11, 14), "valid_to": date(2027, 3, 14)}]
    assert changed == [1]


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"subject": "  "}, {"subject": "required"}),
        ({"subject": "x" * 101}, {"subject": "too_long"}),
        ({"event_type": "EGZAMINAS"}, {"event_type": "invalid_choice"}),
        ({"day_of_week": "MONDAY"}, {"day_of_week": "invalid_choice"}),
        ({"week_pattern": "TRECIA"}, {"week_pattern": "invalid_choice"}),
        ({"start_time": "9am"}, {"start_time": "invalid_time"}),
        ({"start_time": "12:00"}, {"end_time": "end_not_after_start"}),
        ({"room": "x" * 51}, {"room": "too_long"}),
    ],
)
def test_invalid_input_is_rejected_per_field_and_nothing_is_saved(changes, expected):
    changed = []
    service, schedules = make_service(changed)
    row = ReviewRow(**{**ROW.to_dict(), **changes})

    with pytest.raises(ValidationFailed) as exc:
        service.add_event(1, row)

    assert exc.value.errors == expected
    assert schedules.events == {} and changed == []


def test_update_changes_every_field_and_the_change_time_and_notifies():
    changed = []
    service, _ = make_service(changed)
    event = service.add_event(1, ROW)

    updated = service.update_event(
        1, event.id, ReviewRow("Algoritmai", "PRATYBOS", "KETVIRTADIENIS", "12:00", "13:30", "", False, "ANTRA")
    )

    assert (updated.subject_name, updated.weekday.label, updated.room, updated.is_mandatory) == (
        "Algoritmai", "Ketvirtadienis", None, False)
    assert updated.week_pattern == WeekPattern.WEEK_2 and updated.updated_at >= event.updated_at
    assert service.get_event(1, event.id) == updated and changed == [1, 1]


def test_remove_deletes_the_event_and_notifies():
    changed = []
    service, _ = make_service(changed)
    event = service.add_event(1, ROW)

    assert service.remove_event(1, event.id) is True
    assert service.list_events(1) == [] and changed == [1, 1]
    assert service.remove_event(1, event.id) is False and changed == [1, 1]  # nothing changed, nobody notified


def test_a_user_cannot_read_change_or_remove_another_users_event():
    changed = []
    service, _ = make_service(changed)
    event = service.add_event(1, ROW)
    changed.clear()

    assert service.get_event(2, event.id) is None
    assert service.update_event(2, event.id, ROW) is None
    assert service.remove_event(2, event.id) is False
    assert changed == [] and service.get_event(1, event.id) is not None


def test_list_is_ordered_by_weekday_then_time():
    service, _ = make_service()
    service.add_event(1, ReviewRow(**{**ROW.to_dict(), "subject": "B", "day_of_week": "TRECIADIENIS"}))
    service.add_event(1, ReviewRow(**{**ROW.to_dict(), "subject": "C", "start_time": "12:00", "end_time": "13:00"}))
    service.add_event(1, ReviewRow(**{**ROW.to_dict(), "subject": "A"}))

    assert [e.subject_name for e in service.list_events(1)] == ["A", "C", "B"]


def logged_in_client(user_id=1, service=None):
    service = service or make_service()[0]
    client = create_app(services=Services(study_events=service)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client, service


def test_lectures_page_requires_login():
    client = create_app(services=Services(study_events=make_service()[0])).test_client()
    assert client.get("/lectures/").status_code == 302


def test_add_edit_and_remove_over_http_with_confirmation_page():
    client, service = logged_in_client()

    assert client.post("/lectures/", data=FORM).status_code == 302
    page = client.get("/lectures/").get_data(as_text=True)
    assert "Duomenų bazės" in page and "10:00–11:30" in page and "SRK-I-101" in page

    event_id = service.list_events(1)[0].id
    edit_page = client.get(f"/lectures/{event_id}/edit").get_data(as_text=True)
    assert "Keisti paskaitą" in edit_page and 'value="Duomenų bazės"' in edit_page

    assert client.post(f"/lectures/{event_id}/edit", data={**FORM, "subject": "Algoritmai"}).status_code == 302
    assert "Algoritmai" in client.get("/lectures/").get_data(as_text=True)

    confirm = client.get(f"/lectures/{event_id}/remove").get_data(as_text=True)
    assert "Pašalinti paskaitą?" in confirm and "Šio veiksmo atšaukti negalima" in confirm
    assert service.list_events(1)  # still there: the confirmation page itself removes nothing

    assert client.post(f"/lectures/{event_id}/remove").status_code == 302
    assert service.list_events(1) == []


def test_errors_are_shown_next_to_the_fields_in_lithuanian_and_the_form_keeps_the_input():
    client, service = logged_in_client()

    page = client.post(
        "/lectures/", data={**FORM, "subject": "", "start_time": "12:00", "end_time": "11:00"}
    ).get_data(as_text=True)

    assert "Dalykas yra privalomas." in page and "Pabaigos laikas turi būti vėlesnis už pradžios laiką." in page
    assert 'value="12:00"' in page and service.list_events(1) == []


def test_user_cannot_edit_or_remove_another_users_lecture_over_http():
    owner, service = logged_in_client(1)
    owner.post("/lectures/", data=FORM)
    event_id = service.list_events(1)[0].id

    other, _ = logged_in_client(2, service)
    assert other.post(f"/lectures/{event_id}/edit", data={**FORM, "subject": "Hacked"}).status_code == 302
    assert other.post(f"/lectures/{event_id}/remove").status_code == 302
    assert other.get(f"/lectures/{event_id}/edit").status_code == 302  # "not found" redirect

    assert [e.subject_name for e in service.list_events(1)] == ["Duomenų bazės"]
