"""Reminders to upload an updated timetable (F-20, F-21, US-09)."""

from datetime import date

import pytest

from app.application.reminder_service import REMINDER_TEXT, ReminderService
from app.application.schedule_import_service import ScheduleImportService
from app.application.week_view_service import WeekViewService
from app.container import Services
from app.domain.entities import ReminderType
from app.domain.reminder import current_period
from app.infrastructure.config import _parse_semester_starts
from app.web import create_app
from tests import fakes

STARTS = [(9, 1), (2, 1)]


def make_service(today, last_upload=None):
    settings, schedules = fakes.FakeReminderSettingRepository(), fakes.FakeScheduleRepository()
    if last_upload:
        schedules.last_upload[1] = last_upload
    return ReminderService(settings, schedules, STARTS, today=lambda: today), settings, schedules


@pytest.mark.parametrize(
    "today,start,kind",
    [
        (date(2026, 9, 1), date(2026, 9, 1), ReminderType.SEMESTER_START),  # semester wins over the month start
        (date(2026, 9, 20), date(2026, 9, 1), ReminderType.SEMESTER_START),
        (date(2026, 10, 3), date(2026, 10, 1), ReminderType.MONTH_START),
        (date(2027, 2, 1), date(2027, 2, 1), ReminderType.SEMESTER_START),
        (date(2027, 1, 2), date(2027, 1, 1), ReminderType.MONTH_START),
        (date(2026, 1, 15), date(2026, 1, 1), ReminderType.MONTH_START),
    ],
)
def test_current_period(today, start, kind):
    assert current_period(today, STARTS) == (start, kind)


@pytest.mark.parametrize(
    "today,shown",
    [
        (date(2026, 10, 1), True),  # day 0
        (date(2026, 10, 7), True),  # day 6: the last of the first 7 calendar days
        (date(2026, 10, 8), False),  # day 7
        (date(2026, 9, 30), False),
        (date(2026, 9, 3), True),  # inside the semester start window
    ],
)
def test_reminder_is_shown_only_in_the_first_seven_days_of_a_period(today, shown):
    service, *_ = make_service(today)
    reminder = service.get_active_reminder(1)
    assert (reminder is not None) is shown
    if shown:
        assert reminder.text == REMINDER_TEXT


def test_reminder_type_follows_the_period():
    assert make_service(date(2026, 9, 2))[0].get_active_reminder(1).reminder_type == ReminderType.SEMESTER_START
    assert make_service(date(2026, 11, 2))[0].get_active_reminder(1).reminder_type == ReminderType.MONTH_START


def test_no_reminder_when_a_schedule_was_uploaded_since_the_period_began():
    assert make_service(date(2026, 11, 3), last_upload=date(2026, 11, 1))[0].get_active_reminder(1) is None
    assert make_service(date(2026, 11, 3), last_upload=date(2026, 10, 20))[0].get_active_reminder(1) is not None
    assert make_service(date(2026, 11, 3), last_upload=None)[0].get_active_reminder(1) is not None


def test_closing_hides_the_reminder_until_the_next_period():
    service, settings, _ = make_service(date(2026, 11, 3))
    service.close(1)
    assert settings.get(1).closed_period_start == date(2026, 11, 1)
    assert service.get_active_reminder(1) is None

    next_period = ReminderService(settings, fakes.FakeScheduleRepository(), STARTS, today=lambda: date(2026, 12, 2))
    assert next_period.get_active_reminder(1) is not None


def test_disabling_and_enabling_reminders():
    service, _, _ = make_service(date(2026, 11, 3))
    service.disable(1)
    assert service.is_enabled(1) is False and service.get_active_reminder(1) is None
    service.enable(1)
    assert service.is_enabled(1) is True and service.get_active_reminder(1) is not None


def test_settings_are_per_user():
    service, _, _ = make_service(date(2026, 11, 3))
    service.disable(1)
    assert service.get_active_reminder(2) is not None


def test_semester_start_dates_setting():
    assert _parse_semester_starts("09-01, 02-01") == [(9, 1), (2, 1)]
    for bad in ("9", "13-01", "02-30", "abc"):
        with pytest.raises(RuntimeError):
            _parse_semester_starts(bad)


def logged_in_client(today):
    service, settings, schedules = make_service(today)
    week_view = WeekViewService(
        schedules, fakes.FakeWorkShiftRepository(), fakes.FakeConflictRepository(), fakes.FakeNotificationRepository()
    )
    import_service = ScheduleImportService(
        fakes.FakePdfDocumentRepository(), schedules, fakes.FakeRecognizer(), fakes.FakeAiRequestLog()
    )
    client = create_app(
        services=Services(reminders=service, week_view=week_view, schedule_import=import_service)
    ).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    return client, service


def test_reminder_bar_is_shown_on_the_week_and_upload_windows_and_can_be_closed():
    client, service = logged_in_client(date(2026, 11, 3))

    week = client.get("/week/").get_data(as_text=True)
    assert "Prasidėjo naujas laikotarpis." in week and "Įkelkite atnaujintą tvarkaraštį." in week
    assert "Uždaryti" in week and "Išjungti priminimus" in week
    assert "Prasidėjo naujas laikotarpis." in client.get("/schedule/upload").get_data(as_text=True)

    response = client.post("/reminders/close", data={"next": "/schedule/upload"})
    assert response.status_code == 302 and response.headers["Location"].endswith("/schedule/upload")
    assert "Prasidėjo naujas laikotarpis." not in client.get("/week/").get_data(as_text=True)


def test_disabling_from_the_bar_stops_reminders_and_open_redirects_are_ignored():
    client, service = logged_in_client(date(2026, 11, 3))

    response = client.post("/reminders/disable", data={"next": "https://evil.example/"})
    assert response.status_code == 302 and "evil.example" not in response.headers["Location"]
    assert service.is_enabled(1) is False
    assert "Prasidėjo naujas laikotarpis." not in client.get("/week/").get_data(as_text=True)

    client.post("/reminders/enable")
    assert service.is_enabled(1) is True


def test_no_reminder_outside_the_window_and_a_broken_reminder_service_does_not_break_the_page():
    client, _ = logged_in_client(date(2026, 11, 20))
    assert "Prasidėjo naujas laikotarpis." not in client.get("/week/").get_data(as_text=True)

    class Broken:
        def get_active_reminder(self, user_id):
            raise RuntimeError("db down")

    week_view = WeekViewService(
        fakes.FakeScheduleRepository(), fakes.FakeWorkShiftRepository(), fakes.FakeConflictRepository(),
        fakes.FakeNotificationRepository(),
    )
    broken = create_app(services=Services(reminders=Broken(), week_view=week_view)).test_client()
    with broken.session_transaction() as session:
        session["user_id"] = 1
    assert broken.get("/week/").status_code == 200
