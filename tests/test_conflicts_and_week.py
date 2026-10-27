from datetime import date, time

from app.application.conflict_service import ConflictService
from app.application.week_view_service import WeekViewService
from app.container import Services
from app.domain.entities import DetectedConflict, WorkShift
from app.domain.overlap import overlap_minutes
from app.domain.weekday import Weekday
from app.web import create_app
from tests import fakes
from tests.fakes import sample_event


def make_conflicts(analyzer):
    schedules, shifts = fakes.FakeScheduleRepository(), fakes.FakeWorkShiftRepository()
    conflicts, notifications = fakes.FakeConflictRepository(), fakes.FakeNotificationRepository()
    ai_log = fakes.FakeAiRequestLog()
    service = ConflictService(schedules, shifts, conflicts, notifications, analyzer, ai_log)
    return service, schedules, shifts, conflicts, notifications, ai_log


def test_overlap_rule_ignores_touching_intervals():
    shift = WorkShift(1, "Kavine", Weekday.MONDAY, time(10, 30), time(14, 0))
    assert overlap_minutes(sample_event(1, end=time(10, 30)), shift) == 0
    assert overlap_minutes(sample_event(1, end=time(11, 0)), shift) == 30
    assert overlap_minutes(sample_event(1, weekday=Weekday.TUESDAY, end=time(11, 0)), shift) == 0


def test_conflict_check_verifies_ai_result_and_notifies_once():
    # The analyzer "hallucinates" a touching pair (event 2) and a wrong duration for the real one.
    analyzer = fakes.FakeAnalyzer([DetectedConflict(1, 1, 999), DetectedConflict(2, 1, 60)])
    service, schedules, shifts, conflicts, notifications, _ = make_conflicts(analyzer)
    schedules.add(1, None, date.today(), date.today(), [sample_event(), sample_event(weekday=Weekday.TUESDAY)])
    shifts.add(1, "Kavine", Weekday.MONDAY, time(10, 0), time(14, 0))

    service.run_check(1)
    assert [(c.study_event_id, c.overlap_minutes) for c in conflicts.list_active(1)] == [(1, 30)]
    assert [n.message for n in notifications.list_unread(1)] == ["Aptiktas konfliktas: pirmadienis 09:00–10:30"]

    service.run_check(1)  # same result again: no duplicate notification
    assert len(notifications.list_unread(1)) == 1


def test_conflict_check_never_raises_and_keeps_data_on_failure():
    service, schedules, shifts, conflicts, _, ai_log = make_conflicts(fakes.FakeAnalyzer(fail=True))
    schedules.add(1, None, date.today(), date.today(), [sample_event()])
    shifts.add(1, "Kavine", Weekday.MONDAY, time(10, 0), time(14, 0))
    service.run_check(1)
    assert conflicts.list_active(1) == [] and ai_log.requests[0]["error"]  # failure is logged, data unchanged


def test_week_view_marks_conflicts_and_normalizes_to_monday():
    service, schedules, shifts, conflicts, notifications, _ = make_conflicts(
        fakes.FakeAnalyzer([DetectedConflict(1, 1, 30)])
    )
    schedules.add(1, None, date.today(), date.today(), [sample_event()])
    shifts.add(1, "Kavine", Weekday.MONDAY, time(10, 0), time(14, 0))
    service.run_check(1)

    week = WeekViewService(schedules, shifts, conflicts, notifications).get_week(1, date(2026, 10, 28))
    assert week.week_start == date(2026, 10, 26) and week.next_week == date(2026, 11, 2)
    monday, tuesday = week.days[0], week.days[1]
    assert monday.has_conflict and monday.events[0].has_conflict and monday.shifts[0].has_conflict
    assert monday.conflicts[0].overlap_minutes == 30
    assert not tuesday.has_conflict


def test_week_page_shows_conflict_notification_and_dismiss_works():
    service, schedules, shifts, conflicts, notifications, _ = make_conflicts(
        fakes.FakeAnalyzer([DetectedConflict(1, 1, 30)])
    )
    schedules.add(1, None, date.today(), date.today(), [sample_event()])
    shifts.add(1, "Kavine", Weekday.MONDAY, time(10, 0), time(14, 0))
    service.run_check(1)

    week_view = WeekViewService(schedules, shifts, conflicts, notifications)
    client = create_app(services=Services(conflicts=service, week_view=week_view)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1

    page = client.get("/week/2026-10-26").get_data(as_text=True)
    assert "Aptiktas konfliktas: pirmadienis 09:00–10:30" in page
    assert "Sutapimo trukmė" in page and "<b>30 min.</b>" in page

    client.post("/week/notifications/1/dismiss")
    assert "Aptiktas konfliktas: pirmadienis" not in client.get("/week/2026-10-26").get_data(as_text=True)


def test_recheck_button_runs_the_conflict_check_again():
    service, schedules, shifts, conflicts, notifications, ai_log = make_conflicts(
        fakes.FakeAnalyzer([DetectedConflict(1, 1, 30)])
    )
    schedules.add(1, None, date.today(), date.today(), [sample_event()])
    shifts.add(1, "Kavine", Weekday.MONDAY, time(10, 0), time(14, 0))
    week_view = WeekViewService(schedules, shifts, conflicts, notifications)
    client = create_app(services=Services(conflicts=service, week_view=week_view)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1

    assert client.post("/week/recheck").status_code == 302
    assert len(ai_log.requests) == 1 and len(conflicts.list_active(1)) == 1
