"""Full-flow tests across all features: real Flask app and templates, fake repositories underneath."""

import io
from datetime import time

import pytest

from app.application.auth_service import AuthService
from app.application.change_notifier import ChangeNotifier
from app.application.conflict_service import ConflictService
from app.application.schedule_import_service import ScheduleImportService
from app.application.week_view_service import WeekViewService
from app.application.work_shift_service import WorkShiftService
from app.container import Services
from app.domain.entities import DetectedConflict
from app.web import create_app
from tests import fakes


@pytest.fixture
def client():
    users, pdfs = fakes.FakeUserRepository(), fakes.FakePdfDocumentRepository()
    schedules, shifts = fakes.FakeScheduleRepository(), fakes.FakeWorkShiftRepository()
    conflict_repo, notifications = fakes.FakeConflictRepository(), fakes.FakeNotificationRepository()
    ai_log = fakes.FakeAiRequestLog()
    conflicts = ConflictService(
        schedules, shifts, conflict_repo, notifications, fakes.FakeAnalyzer([DetectedConflict(1, 1, 30)]), ai_log
    )
    change_notifier = ChangeNotifier()
    change_notifier.subscribe(conflicts.run_check)
    services = Services(
        auth=AuthService(users, fakes.FakeHasher()),
        schedule_import=ScheduleImportService(pdfs, schedules, fakes.FakeRecognizer(), ai_log, change_notifier),
        work_shifts=WorkShiftService(shifts, change_notifier),
        conflicts=conflicts,
        week_view=WeekViewService(schedules, shifts, conflict_repo, notifications),
    )
    return create_app(services=services).test_client()


def register(client):
    return client.post("/register", data={"name": "Jonas", "email": "j@x.lt", "password": "Slaptazodis123"})


def test_anonymous_users_are_redirected_to_login(client):
    for url in ("/work-shifts/", "/schedule/upload", "/week/"):
        response = client.get(url)
        assert response.status_code == 302 and response.headers["Location"].endswith("/login")


def test_register_login_logout_and_error_messages_are_lithuanian(client):
    response = client.post("/register", data={"name": "J", "email": "bad", "password": "short"})
    assert "Neteisingas el. pašto formatas" in response.get_data(as_text=True)
    assert register(client).status_code == 302
    client.post("/logout")
    wrong = client.post("/login", data={"email": "j@x.lt", "password": "wrong"})
    assert "Neteisingas el. paštas arba slaptažodis" in wrong.get_data(as_text=True)
    assert client.post("/login", data={"email": "j@x.lt", "password": "Slaptazodis123"}).status_code == 302


def test_full_flow_upload_review_confirm_and_conflict_in_week_view(client):
    register(client)
    client.post(
        "/work-shifts/add",
        data={"workplace_name": "Kavine", "day_of_week": "Pirmadienis", "start_time": "10:00", "end_time": "14:00"},
    )

    upload = client.post(
        "/schedule/upload",
        data={"pdf_file": (io.BytesIO(b"%PDF-1.4"), "t.pdf"), "ai_consent": "on"},
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

    assert client.post("/schedule/review", data={**row, "action": "confirm"}).status_code == 302

    page = client.get("/week/2026-10-26").get_data(as_text=True)
    assert "Aptiktas konfliktas: pirmadienis 09:00–10:30" in page
    assert "Sutapimo trukmė: 30 min." in page


def test_upload_rejects_missing_consent(client):
    register(client)
    response = client.post(
        "/schedule/upload",
        data={"pdf_file": (io.BytesIO(b"%PDF"), "t.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200 and "sutikimą" in response.get_data(as_text=True)


def test_user_cannot_remove_another_users_shift(client):
    register(client)
    client.post(
        "/work-shifts/add",
        data={"workplace_name": "Kavine", "day_of_week": "Pirmadienis", "start_time": "10:00", "end_time": "14:00"},
    )
    client.post("/logout")
    client.post("/register", data={"name": "Kitas", "email": "k@x.lt", "password": "Slaptazodis123"})
    client.post("/work-shifts/1/remove")
    client.post("/logout")
    client.post("/login", data={"email": "j@x.lt", "password": "Slaptazodis123"})
    assert "Kavine" in client.get("/work-shifts/").get_data(as_text=True)
