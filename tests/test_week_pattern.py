"""Lectures that take place only on week 1 or week 2 (academic weeks start with the week of 1 September)."""

from datetime import date, time

import pytest

from app.application.errors import ValidationFailed
from app.application.schedule_import_service import ReviewRow
from app.application.week_view_service import WeekViewService
from app.domain.academic_week import academic_anchor, pattern_applies, week_number
from app.domain.entities import WeekPattern, WorkShift
from app.domain.overlap import overlap_minutes
from app.infrastructure.ai.gemini_schedule_recognizer import parse_events, parse_validity
from tests import fakes
from tests.fakes import sample_event
from tests.test_ai_adapters import GOOD_ENTRY
from tests.test_schedule_import import make_import


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 8, 31), 1),  # Monday of the week that contains 1 September 2026 (a Tuesday)
        (date(2026, 9, 1), 1),
        (date(2026, 9, 6), 1),  # Sunday of week 1
        (date(2026, 9, 7), 2),
        (date(2026, 9, 14), 1),
        (date(2026, 11, 16), 2),
        (date(2026, 11, 25), 1),
        (date(2026, 12, 31), 2),  # 17 weeks after the start
        (date(2027, 1, 4), 1),  # the count continues over the new year
        (date(2027, 2, 8), 2),  # ... and into the spring semester, without restarting
        (date(2027, 2, 15), 1),
    ],
)
def test_week_number_counts_from_the_week_of_1_september(day, expected):
    assert week_number(day) == expected


def test_spring_dates_use_the_september_anchor_of_the_academic_year():
    assert academic_anchor(date(2027, 2, 10)) == date(2026, 8, 31)
    assert academic_anchor(date(2026, 8, 30)) == date(2025, 9, 1)  # still the previous academic year
    assert academic_anchor(date(2026, 8, 31)) == date(2026, 8, 31)


def test_pattern_applies():
    assert pattern_applies(WeekPattern.EVERY_WEEK, date(2026, 9, 7))
    assert pattern_applies(WeekPattern.WEEK_1, date(2026, 9, 1)) and not pattern_applies(WeekPattern.WEEK_1, date(2026, 9, 8))
    assert pattern_applies(WeekPattern.WEEK_2, date(2026, 9, 8)) and not pattern_applies(WeekPattern.WEEK_2, date(2026, 9, 1))


def test_shift_conflicts_only_with_lectures_of_its_study_week():
    week_2_lecture = sample_event(1, week_pattern=WeekPattern.WEEK_2)
    shift_in_week_1 = WorkShift(1, "Kavine", date(2026, 9, 14), time(9, 0), time(12, 0))  # Monday, week 1
    shift_in_week_2 = WorkShift(2, "Kavine", date(2026, 9, 7), time(9, 0), time(12, 0))  # Monday, week 2

    assert overlap_minutes(week_2_lecture, shift_in_week_1) == 0
    assert overlap_minutes(week_2_lecture, shift_in_week_2) == 90
    assert overlap_minutes(sample_event(1), shift_in_week_1) == 90  # a weekly lecture conflicts in both weeks


def test_week_view_shows_alternating_lectures_only_in_their_week():
    schedules, shifts = fakes.FakeScheduleRepository(), fakes.FakeWorkShiftRepository()
    schedules.add(1, None, date(2026, 9, 1), date(2026, 12, 20), [
        sample_event(subject="Kiekvieną savaitę"),
        sample_event(subject="Tik 1 savaitė", week_pattern=WeekPattern.WEEK_1),
        sample_event(subject="Tik 2 savaitė", week_pattern=WeekPattern.WEEK_2),
    ])
    week_view = WeekViewService(schedules, shifts, fakes.FakeConflictRepository(), fakes.FakeNotificationRepository())

    week_1 = week_view.get_week(1, date(2026, 9, 14))
    week_2 = week_view.get_week(1, date(2026, 9, 7))

    assert week_1.week_number == 1 and week_2.week_number == 2
    assert [e.event.subject_name for e in week_1.days[0].events] == ["Kiekvieną savaitę", "Tik 1 savaitė"]
    assert [e.event.subject_name for e in week_2.days[0].events] == ["Kiekvieną savaitę", "Tik 2 savaitė"]


@pytest.mark.parametrize(
    "value,expected",
    [(None, WeekPattern.EVERY_WEEK), (0, WeekPattern.EVERY_WEEK), ("", WeekPattern.EVERY_WEEK),
     (1, WeekPattern.WEEK_1), ("2", WeekPattern.WEEK_2)],
)
def test_recognizer_reads_the_week_column(value, expected):
    [event] = parse_events({"events": [{**GOOD_ENTRY, "week": value}]})
    assert event.week_pattern == expected


def test_recognizer_without_week_field_means_every_week_and_bad_value_is_rejected():
    assert parse_events([GOOD_ENTRY])[0].week_pattern == WeekPattern.EVERY_WEEK
    with pytest.raises(ValueError):
        parse_events([{**GOOD_ENTRY, "week": 3}])


def test_recognizer_validity_period_is_optional_and_checked():
    assert parse_validity({"valid_from": "2026-09-01", "valid_to": "2026-12-20", "events": []}) == (
        date(2026, 9, 1), date(2026, 12, 20))
    assert parse_validity({"valid_from": "2026-12-20", "valid_to": "2026-09-01"}) == (None, None)
    assert parse_validity({"valid_from": "soon"}) == (None, None)
    assert parse_validity([GOOD_ENTRY]) == (None, None)


def test_confirm_keeps_the_week_pattern_and_uses_the_given_period():
    service, _, schedules, _ = make_import()
    upload = service.upload_and_recognize(1, "t.pdf", b"%PDF", True)
    row = ReviewRow("Programavimas", "PASKAITA", "PIRMADIENIS", "09:00", "10:30", "A1", True, "ANTRA")

    service.confirm(1, upload.pdf_document_id, [row], "2026-09-01", "2026-12-20")

    assert schedules.saved_schedules[0]["valid_from"] == date(2026, 9, 1)
    assert schedules.saved_schedules[0]["valid_to"] == date(2026, 12, 20)
    assert schedules.events[1][0].week_pattern == WeekPattern.WEEK_2


def test_confirm_rejects_an_invalid_week_pattern_and_an_invalid_period():
    service, _, schedules, _ = make_import()
    upload = service.upload_and_recognize(1, "t.pdf", b"%PDF", True)

    bad_row = ReviewRow("Programavimas", "PASKAITA", "PIRMADIENIS", "09:00", "10:30", "A1", True, "TRECIA")
    with pytest.raises(Exception) as exc:
        service.confirm(1, upload.pdf_document_id, [bad_row])
    assert exc.value.errors == [{"week_pattern": "invalid_choice"}]

    with pytest.raises(ValidationFailed) as exc:
        service.confirm(1, upload.pdf_document_id, upload.rows, "2026-12-20", "2026-09-01")
    assert exc.value.errors == {"valid_to": "end_not_after_start"}
    with pytest.raises(ValidationFailed) as exc:
        service.confirm(1, upload.pdf_document_id, upload.rows, "2026-09-01", "")
    assert exc.value.errors == {"valid_to": "invalid_date"}
    assert schedules.saved_schedules == []


def test_review_page_shows_week_column_and_period_and_saves_them():
    import io

    from app.container import Services
    from app.web import create_app

    service, _, schedules, _ = make_import(fakes.FakeRecognizer([sample_event(week_pattern=WeekPattern.WEEK_2)]))
    client = create_app(services=Services(schedule_import=service)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    client.post(
        "/schedule/upload",
        data={"pdf_file": (io.BytesIO(b"%PDF"), "t.pdf"), "ai_consent": "on"},
        content_type="multipart/form-data",
    )

    page = client.get("/schedule/review").get_data(as_text=True)
    assert "Savaitė" in page and 'value="ANTRA" selected' in page and 'name="valid_from"' in page

    row = {
        "row_count": "1", "subject_0": "Programavimas", "event_type_0": "PASKAITA", "day_of_week_0": "PIRMADIENIS",
        "start_time_0": "09:00", "end_time_0": "10:30", "room_0": "A1", "is_mandatory_0": "on",
        "week_pattern_0": "PIRMA", "action": "confirm",
    }
    bad = client.post("/schedule/review", data={**row, "valid_from": "2026-12-20", "valid_to": "2026-09-01"})
    assert "Pabaigos data turi būti vėlesnė" in bad.get_data(as_text=True) and schedules.saved_schedules == []

    ok = client.post("/schedule/review", data={**row, "valid_from": "2026-09-01", "valid_to": "2026-12-20"})
    assert ok.status_code == 302 and schedules.events[1][0].week_pattern == WeekPattern.WEEK_1
