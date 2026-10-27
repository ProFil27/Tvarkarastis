import io
from datetime import date

import pytest

from app.application.errors import RecognitionFailed, RowsValidationFailed, ValidationFailed
from app.application.schedule_import_service import ReviewRow, ScheduleImportService
from app.container import Services
from app.domain.entities import PdfStatus
from app.web import create_app
from tests import fakes


def make_import(recognizer=None, on_saved=lambda user_id: None):
    pdfs, schedules = fakes.FakePdfDocumentRepository(), fakes.FakeScheduleRepository()
    ai_log = fakes.FakeAiRequestLog()
    service = ScheduleImportService(
        pdfs, schedules, recognizer or fakes.FakeRecognizer(), ai_log, on_saved, today=lambda: date(2026, 10, 27)
    )
    return service, pdfs, schedules, ai_log


@pytest.mark.parametrize(
    "filename,size,consent,code",
    [
        ("t.txt", 1, True, "not_pdf"),
        ("t.pdf", 10 * 1024 * 1024 + 1, True, "too_large"),
        ("t.pdf", 1, False, "consent_required"),
    ],
)
def test_upload_validation(filename, size, consent, code):
    service, *_ = make_import()
    with pytest.raises(ValidationFailed) as exc:
        service.upload_and_recognize(1, filename, b"x" * size, consent)
    assert exc.value.errors == {"file": code}


def test_upload_recognition_success_and_failure_update_status():
    service, pdfs, _, _ = make_import()
    result = service.upload_and_recognize(1, "t.pdf", b"%PDF", True)
    assert pdfs.documents[result.pdf_document_id].status == PdfStatus.RECOGNIZED
    assert result.rows[0].subject == "Programavimas" and result.rows[0].start_time == "09:00"

    failing, pdfs, _, ai_log = make_import(fakes.FakeRecognizer(fail=True))
    with pytest.raises(RecognitionFailed):
        failing.upload_and_recognize(1, "t.pdf", b"%PDF", True)
    assert pdfs.documents[1].status == PdfStatus.FAILED
    assert ai_log.requests[0]["error"] == "boom"


def test_confirm_saves_only_valid_rows_and_notifies_listener():
    saved = []
    service, pdfs, schedules, _ = make_import(on_saved=saved.append)
    upload = service.upload_and_recognize(1, "t.pdf", b"%PDF", True)

    bad = ReviewRow("Programavimas", "PASKAITA", "PIRMADIENIS", "11:00", "10:00", "A1", True)
    with pytest.raises(RowsValidationFailed) as exc:
        service.confirm(1, upload.pdf_document_id, [bad])
    assert exc.value.errors == [{"end_time": "end_not_after_start"}]
    assert schedules.saved_schedules == [] and saved == []

    service.confirm(1, upload.pdf_document_id, upload.rows)
    assert pdfs.documents[upload.pdf_document_id].status == PdfStatus.CONFIRMED
    assert schedules.saved_schedules[0]["valid_to"] == date(2027, 2, 24)  # today + 120 days
    assert saved == [1]


def test_upload_review_confirm_flow_over_http():
    service, _, schedules, _ = make_import()
    client = create_app(services=Services(schedule_import=service)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1

    missing_consent = client.post(
        "/schedule/upload", data={"pdf_file": (io.BytesIO(b"%PDF"), "t.pdf")}, content_type="multipart/form-data"
    )
    assert "sutikimą" in missing_consent.get_data(as_text=True)

    upload = client.post(
        "/schedule/upload",
        data={"pdf_file": (io.BytesIO(b"%PDF"), "t.pdf"), "ai_consent": "on"},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 302 and upload.headers["Location"].endswith("/schedule/review")
    assert "Programavimas" in client.get("/schedule/review").get_data(as_text=True)

    row = {
        "row_count": "1", "subject_0": "Programavimas", "event_type_0": "PASKAITA", "day_of_week_0": "PIRMADIENIS",
        "start_time_0": "09:00", "end_time_0": "10:30", "room_0": "A1", "is_mandatory_0": "on",
    }
    invalid = client.post("/schedule/review", data={**row, "end_time_0": "08:00", "action": "confirm"})
    assert "vėlesnis už pradžios laiką" in invalid.get_data(as_text=True)
    assert schedules.saved_schedules == []

    assert client.post("/schedule/review", data={**row, "action": "confirm"}).status_code == 302
    assert len(schedules.saved_schedules) == 1
