"""Work shifts that repeat every week are one series: edited, removed and exported to Google Calendar as a whole."""

from datetime import date, time

import pytest

from app.application.calendar_events import shift_series_body
from app.application.change_notifier import ChangeNotifier
from app.application.errors import ValidationFailed
from app.application.work_shift_service import WorkShiftService
from app.container import Services
from app.web import create_app
from tests.test_calendar_export import World

WEDNESDAYS_UNTIL = "2026-12-09"  # from 2026-09-09: 14 Wednesdays


class Setup:
    """A connected user who already exported a weekly series of work shifts."""

    def __init__(self):
        self.world = World()
        notifier = ChangeNotifier()
        self.shifts = WorkShiftService(self.world.shifts, notifier, self.world.series)
        notifier.subscribe(self.world.service.on_data_changed)
        self.first_export = None

    def export_series(self):
        self.created = self.shifts.add_weekly_shifts(1, "Kavinė", "2026-09-09", "15:00", "19:00", WEDNESDAYS_UNTIL)
        self.world.service.export(1)
        return self.created

    def google_series(self):
        [body] = self.world.provider.events.values()
        return body

    def calls(self, name):
        return len(self.world.provider.calls_named(name))


def test_a_weekly_series_is_one_recurring_google_event_not_one_event_per_week():
    setup = Setup()
    shifts = setup.export_series()

    assert len(shifts) == 14 and setup.calls("create_event") == 1  # 1 request instead of 14
    body = setup.google_series()
    assert body["summary"] == "Darbas: Kavinė" and body["start"]["dateTime"] == "2026-09-09T15:00:00"
    assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;UNTIL=20261209T235959Z"]
    [link] = setup.world.links.list_links(1)
    assert link.shift_series_id is not None and link.work_shift_id is None


def test_editing_the_whole_series_is_one_change_and_one_google_update():
    setup = Setup()
    setup.export_series()
    series_id = setup.created[0].series_id

    updated = setup.shifts.update_series(1, series_id, "Naujas darbas", "16:00", "20:30", WEDNESDAYS_UNTIL)

    assert updated.workplace_name == "Naujas darbas"
    assert {(s.workplace_name, s.start_time) for s in setup.shifts.list_shifts(1)} == {("Naujas darbas", time(16, 0))}
    assert setup.calls("update_event") == 1 and setup.calls("create_event") == 1
    assert setup.google_series()["start"]["dateTime"] == "2026-09-09T16:00:00"


def test_extending_and_shortening_a_series():
    setup = Setup()
    setup.export_series()
    series_id = setup.created[0].series_id

    setup.shifts.update_series(1, series_id, "Kavinė", "15:00", "19:00", "2026-12-23")  # two more Wednesdays
    assert len(setup.shifts.list_shifts(1)) == 16
    assert setup.google_series()["recurrence"][0].endswith("UNTIL=20261223T235959Z")

    setup.shifts.update_series(1, series_id, "Kavinė", "15:00", "19:00", "2026-09-30")  # only 4 weeks
    assert [s.work_date.isoformat() for s in setup.shifts.list_shifts(1)] == [
        "2026-09-09", "2026-09-16", "2026-09-23", "2026-09-30"]
    assert setup.google_series()["recurrence"][0].endswith("UNTIL=20260930T235959Z")
    assert setup.calls("create_event") == 1


def test_removing_one_day_excludes_it_from_the_google_series():
    setup = Setup()
    shifts = setup.export_series()

    setup.shifts.remove_shift(1, shifts[3].id)  # 2026-09-30

    recurrence = setup.google_series()["recurrence"]
    assert recurrence[1:] == ["EXDATE;TZID=Europe/Vilnius:20260930T150000"]
    assert len(setup.shifts.list_shifts(1)) == 13 and setup.calls("update_event") == 1


def test_a_day_changed_on_its_own_becomes_an_exception_and_is_not_touched_by_the_series():
    setup = Setup()
    shifts = setup.export_series()
    changed_day = shifts[2]  # 2026-09-23

    setup.shifts.update_shift(1, changed_day.id, "Kavinė", "2026-09-23", "10:00", "12:00")
    setup.shifts.update_series(1, changed_day.series_id, "Kita vieta", "16:00", "20:00", WEDNESDAYS_UNTIL)

    by_date = {s.work_date: s for s in setup.shifts.list_shifts(1)}
    assert by_date[date(2026, 9, 23)].is_exception and by_date[date(2026, 9, 23)].start_time == time(10, 0)
    assert by_date[date(2026, 9, 23)].workplace_name == "Kavinė"  # the series edit left it alone
    assert by_date[date(2026, 9, 16)].workplace_name == "Kita vieta"
    # in Google: the series skips that day and the exception is its own event
    summaries = sorted(body["summary"] for body in setup.world.provider.events.values())
    assert summaries == ["Darbas: Kavinė", "Darbas: Kita vieta"]
    series_event = next(b for b in setup.world.provider.events.values() if b["summary"] == "Darbas: Kita vieta")
    assert "EXDATE;TZID=Europe/Vilnius:20260923T160000" in series_event["recurrence"]
    assert len(setup.world.provider.events) == 2


def test_removing_the_whole_series_deletes_its_google_event():
    setup = Setup()
    shifts = setup.export_series()
    series_id = shifts[0].series_id

    assert setup.shifts.remove_series(1, series_id) is True
    setup.world.links.unlink_series(series_id)  # what ON DELETE SET NULL does in the database
    setup.world.service.on_data_changed(1)

    assert setup.shifts.list_shifts(1) == [] and setup.world.provider.events == {}
    assert setup.calls("delete_event") == 1


def test_a_series_whose_last_shift_is_removed_disappears():
    setup = Setup()
    shifts = setup.shifts.add_weekly_shifts(1, "Kavinė", "2026-09-09", "15:00", "19:00", "2026-09-16")
    for shift in shifts:
        setup.shifts.remove_shift(1, shift.id)

    assert setup.shifts.get_series(1, shifts[0].series_id) is None


def test_series_belong_to_their_owner():
    setup = Setup()
    series_id = setup.export_series()[0].series_id

    assert setup.shifts.get_series(2, series_id) is None
    assert setup.shifts.update_series(2, series_id, "X", "10:00", "11:00", WEDNESDAYS_UNTIL) is None
    assert setup.shifts.remove_series(2, series_id) is False
    assert len(setup.shifts.list_shifts(1)) == 14


@pytest.mark.parametrize(
    "args,errors",
    [
        (("", "15:00", "19:00", WEDNESDAYS_UNTIL), {"workplace_name": "required"}),
        (("K", "19:00", "15:00", WEDNESDAYS_UNTIL), {"end_time": "end_not_after_start"}),
        (("K", "15:00", "19:00", "2026-09-01"), {"repeat_until": "before_start"}),
        (("K", "15:00", "19:00", "bad"), {"repeat_until": "invalid_date"}),
    ],
)
def test_series_edit_is_validated_and_changes_nothing(args, errors):
    setup = Setup()
    series_id = setup.export_series()[0].series_id

    with pytest.raises(ValidationFailed) as exc:
        setup.shifts.update_series(1, series_id, *args)

    assert exc.value.errors == errors and setup.calls("update_event") == 0


def test_series_event_body_excludes_the_weeks_without_a_shift():
    days = [date(2026, 9, 9), date(2026, 9, 16), date(2026, 9, 30), date(2026, 10, 14)]  # 23 Sep and 7 Oct are missing

    body = shift_series_body("Kavinė", time(9, 30), time(13, 0), days)

    assert body["recurrence"] == [
        "RRULE:FREQ=WEEKLY;UNTIL=20261014T235959Z",
        "EXDATE;TZID=Europe/Vilnius:20260923T093000",
        "EXDATE;TZID=Europe/Vilnius:20261007T093000",
    ]
    assert "recurrence" not in shift_series_body("Kavinė", time(9, 30), time(13, 0), [date(2026, 9, 9)])


def logged_in(setup):
    client = create_app(services=Services(work_shifts=setup.shifts, calendar=setup.world.service)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    return client


def test_series_pages_edit_and_remove_with_confirmation():
    setup = Setup()
    series_id = setup.export_series()[0].series_id
    client = logged_in(setup)

    listing = client.get("/work-shifts/").get_data(as_text=True)
    assert "Kas savaitę" in listing and f"/work-shifts/series/{series_id}/edit" in listing

    page = client.get(f"/work-shifts/series/{series_id}/edit").get_data(as_text=True)
    assert "Keisti seriją nuo 2026-09-09" in page and 'value="2026-12-09"' in page and "Šalinti visą seriją" in page

    bad = client.post(f"/work-shifts/series/{series_id}/edit", data={
        "workplace_name": "", "start_time": "15:00", "end_time": "19:00", "repeat_until": WEDNESDAYS_UNTIL})
    assert "Darbovietė yra privaloma." in bad.get_data(as_text=True)

    ok = client.post(f"/work-shifts/series/{series_id}/edit", data={
        "workplace_name": "Naujas", "start_time": "16:00", "end_time": "19:00", "repeat_until": WEDNESDAYS_UNTIL})
    assert ok.status_code == 302 and "Naujas" in client.get("/work-shifts/").get_data(as_text=True)

    confirm = client.get(f"/work-shifts/series/{series_id}/remove").get_data(as_text=True)
    assert "Pašalinti visą pamainų seriją?" in confirm and len(setup.shifts.list_shifts(1)) == 14  # nothing removed yet
    assert client.post(f"/work-shifts/series/{series_id}/remove").status_code == 302
    assert setup.shifts.list_shifts(1) == []


def test_another_user_cannot_open_or_remove_a_series():
    setup = Setup()
    series_id = setup.export_series()[0].series_id
    other = create_app(services=Services(work_shifts=setup.shifts)).test_client()
    with other.session_transaction() as session:
        session["user_id"] = 2

    assert other.get(f"/work-shifts/series/{series_id}/edit").status_code == 302
    other.post(f"/work-shifts/series/{series_id}/remove")
    assert len(setup.shifts.list_shifts(1)) == 14
