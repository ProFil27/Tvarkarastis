"""Uploading a schedule that replaces the current one (F-22, F-23, US-10)."""

import io

import pytest

from app.application.errors import ReplaceConfirmationRequired
from app.container import Services
from app.web import create_app
from tests import fakes
from tests.fakes import sample_event
from tests.test_schedule_import import make_import

OLD = [sample_event(subject="Senas 1"), sample_event(subject="Senas 2")]


def service_with_old_schedule(**kwargs):
    saved = []
    service, pdfs, schedules, ai_log = make_import(
        fakes.FakeRecognizer([sample_event(subject="Naujas")]), on_saved=saved.append
    )
    schedules.add(1, None, None, None, OLD)
    return service, pdfs, schedules, saved


def test_replace_flag_is_stored_with_the_pdf_and_nothing_is_removed_on_upload():
    service, pdfs, schedules, saved = service_with_old_schedule()

    result = service.upload_and_recognize(1, "t.pdf", b"%PDF", True, replace_existing=True)

    assert pdfs.documents[result.pdf_document_id].replace_existing is True
    assert schedules.count_events(1) == 2 and schedules.replaced == [] and saved == []  # F-22: old schedule untouched


def test_default_is_not_to_replace_and_the_new_schedule_is_added_next_to_the_old_one():
    service, pdfs, schedules, saved = service_with_old_schedule()
    result = service.upload_and_recognize(1, "t.pdf", b"%PDF", True)
    assert pdfs.documents[result.pdf_document_id].replace_existing is False

    service.confirm(1, result.pdf_document_id, result.rows)

    assert schedules.count_events(1) == 3 and schedules.replaced == []


def test_confirming_without_the_users_consent_raises_and_changes_nothing():
    service, pdfs, schedules, saved = service_with_old_schedule()
    result = service.upload_and_recognize(1, "t.pdf", b"%PDF", True, replace_existing=True)

    with pytest.raises(ReplaceConfirmationRequired) as exc:
        service.confirm(1, result.pdf_document_id, result.rows)

    assert exc.value.event_count == 2
    assert schedules.count_events(1) == 2 and schedules.replaced == [] and saved == []
    assert pdfs.documents[result.pdf_document_id].status.name == "RECOGNIZED"  # not confirmed yet


def test_confirmed_replacement_removes_the_old_events_and_saves_the_new_ones_together():
    service, pdfs, schedules, saved = service_with_old_schedule()
    result = service.upload_and_recognize(1, "t.pdf", b"%PDF", True, replace_existing=True)

    service.confirm(1, result.pdf_document_id, result.rows, replace_confirmed=True)

    assert schedules.replaced == [1]
    assert [e.subject_name for e in schedules.list_study_events(1)] == ["Naujas"]
    assert pdfs.documents[result.pdf_document_id].status.name == "CONFIRMED" and saved == [1]  # conflicts re-checked


def test_replacing_when_there_is_nothing_to_replace_just_saves():
    service, pdfs, schedules, _ = make_import()
    result = service.upload_and_recognize(1, "t.pdf", b"%PDF", True, replace_existing=True)

    service.confirm(1, result.pdf_document_id, result.rows)  # no confirmation needed: nothing would be removed

    assert schedules.count_events(1) == 1 and schedules.replaced == []


def test_only_the_owners_pdf_can_trigger_a_replacement():
    service, pdfs, schedules, saved = service_with_old_schedule()
    result = service.upload_and_recognize(2, "t.pdf", b"%PDF", True, replace_existing=True)  # user 2's document

    service.confirm(1, result.pdf_document_id, result.rows)  # user 1 saves it: the flag is not theirs

    assert schedules.replaced == [] and schedules.count_events(1) == 3


def upload(client, replace):
    data = {"pdf_file": (io.BytesIO(b"%PDF"), "t.pdf"), "ai_consent": "on"}
    if replace:
        data["replace_existing"] = "on"
    client.post("/schedule/upload", data=data, content_type="multipart/form-data")


ROW = {
    "row_count": "1", "subject_0": "Naujas", "event_type_0": "PASKAITA", "day_of_week_0": "PIRMADIENIS",
    "week_pattern_0": "KIEKVIENA", "start_time_0": "09:00", "end_time_0": "10:30", "room_0": "A1",
    "is_mandatory_0": "on",
}


def http_client():
    service, pdfs, schedules, saved = service_with_old_schedule()
    client = create_app(services=Services(schedule_import=service)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    return client, schedules


def test_upload_window_has_the_replace_option():
    client, _ = http_client()
    page = client.get("/schedule/upload").get_data(as_text=True)
    assert "Pakeisti esamą tvarkaraštį" in page and 'name="replace_existing"' in page


def test_confirmation_page_shows_the_count_and_cancel_keeps_the_old_schedule():
    client, schedules = http_client()
    upload(client, replace=True)

    page = client.post("/schedule/review", data={**ROW, "action": "confirm"}).get_data(as_text=True)
    assert "Bus pašalinta 2 ankstesnio tvarkaraščio įrašų. Tęsti?" in page
    assert "Pašalinti ir išsaugoti" in page and "Atšaukti" in page
    assert schedules.count_events(1) == 2 and schedules.replaced == []

    cancel = client.post("/schedule/review", data={**ROW, "action": "cancel_replace"}, follow_redirects=True)
    assert "Senasis tvarkaraštis nepakeistas." in cancel.get_data(as_text=True)
    assert schedules.count_events(1) == 2 and schedules.replaced == []


def test_confirming_the_removal_replaces_the_schedule():
    client, schedules = http_client()
    upload(client, replace=True)

    response = client.post("/schedule/review", data={**ROW, "action": "confirm_replace"})

    assert response.status_code == 302
    assert [e.subject_name for e in schedules.list_study_events(1)] == ["Naujas"]


def test_without_the_option_no_confirmation_is_asked():
    client, schedules = http_client()
    upload(client, replace=False)

    assert client.post("/schedule/review", data={**ROW, "action": "confirm"}).status_code == 302
    assert schedules.count_events(1) == 3
