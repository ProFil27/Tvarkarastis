"""Exporting the schedule to Google Calendar (F-26, F-27, F-29, N-26, N-29..N-32, N-35, N-45, US-12)."""

from dataclasses import replace
from datetime import date, datetime, time

import pytest

from app.application.calendar_events import first_occurrence, study_event_body, work_shift_body
from app.application.calendar_sync_service import CalendarSyncService
from app.application.errors import CalendarError
from app.container import Services
from app.domain.entities import CalendarAccountStatus, StudyEvent, StudyEventType, SyncStatus, WeekPattern, WorkShift
from app.domain.weekday import Weekday
from app.web import create_app
from tests import fakes

FROM, TO = date(2026, 9, 1), date(2026, 12, 20)  # 1 September 2026 is a Tuesday


def lecture(subject="Duomenų bazės", weekday=Weekday.TUESDAY, pattern=WeekPattern.EVERY_WEEK, room="SRK-I-101",
            start=time(10, 0), end=time(11, 30), mandatory=True):
    return StudyEvent(None, subject, StudyEventType.LECTURE, weekday, start, end, room, mandatory, FROM, TO, pattern)


# ----------------------------------------------------------------------------- Google event bodies (N-26)

def test_weekly_lecture_becomes_a_recurring_event_in_the_local_time_zone_with_minute_precision():
    body = study_event_body(lecture(start=time(9, 30)), FROM)

    assert body["summary"] == "Duomenų bazės (paskaita)" and body["location"] == "SRK-I-101"
    assert body["start"] == {"dateTime": "2026-09-01T09:30:00", "timeZone": "Europe/Vilnius"}
    assert body["end"] == {"dateTime": "2026-09-01T11:30:00", "timeZone": "Europe/Vilnius"}
    assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;UNTIL=20261220T235959Z"]


@pytest.mark.parametrize(
    "pattern,first_day,interval",
    [
        (WeekPattern.EVERY_WEEK, date(2026, 9, 1), False),
        (WeekPattern.WEEK_1, date(2026, 9, 1), True),  # the Tuesday of the week that contains 1 September
        (WeekPattern.WEEK_2, date(2026, 9, 8), True),
    ],
)
def test_alternating_lectures_start_in_their_own_week_and_repeat_every_second_week(pattern, first_day, interval):
    body = study_event_body(lecture(pattern=pattern), FROM)

    assert body["start"]["dateTime"].startswith(first_day.isoformat())
    assert ("INTERVAL=2" in body["recurrence"][0]) is interval


def test_first_occurrence_follows_the_weekday_and_skips_events_that_never_take_place():
    assert first_occurrence(lecture(weekday=Weekday.MONDAY), FROM) == date(2026, 9, 7)  # Monday after the Tuesday start
    assert first_occurrence(lecture(weekday=Weekday.MONDAY, pattern=WeekPattern.WEEK_1), FROM) == date(2026, 9, 14)
    short = replace(lecture(weekday=Weekday.MONDAY), valid_to=date(2026, 9, 3))
    assert first_occurrence(short, FROM) is None and study_event_body(short, FROM) is None


def test_summary_is_limited_to_1024_characters_and_optional_fields_are_left_out():
    body = study_event_body(lecture(subject="x" * 2000, room=None, mandatory=False), FROM)
    assert len(body["summary"]) == 1024 and "location" not in body and "neprivaloma" in body["description"]


def test_work_shift_is_a_single_event_on_its_date():
    body = work_shift_body(WorkShift(1, "Kavinė Rytas", date(2026, 11, 16), time(15, 0), time(19, 0)))

    assert body["summary"] == "Darbas: Kavinė Rytas" and "recurrence" not in body
    assert body["start"] == {"dateTime": "2026-11-16T15:00:00", "timeZone": "Europe/Vilnius"}
    assert body["end"]["dateTime"] == "2026-11-16T19:00:00"


# ----------------------------------------------------------------------------- the export itself

class World:
    """A service wired to in-memory fakes, with one connected account."""

    def __init__(self, provider=None, connected=True):
        self.provider = provider or fakes.FakeCalendarProvider()
        self.schedules, self.shifts = fakes.FakeScheduleRepository(), fakes.FakeWorkShiftRepository()
        self.series = fakes.FakeShiftSeriesRepository(self.shifts)
        self.accounts, self.links = fakes.FakeCalendarAccountRepository(), fakes.FakeCalendarEventRepository()
        self.operations, self.cipher = fakes.FakeSyncOperationRepository(), fakes.FakeTokenCipher()
        self.notifications = fakes.FakeNotificationRepository()
        self.service = CalendarSyncService(
            self.provider, self.accounts, self.cipher, self.links, self.operations, self.schedules, self.shifts,
            self.series, self.notifications, now=datetime.now, utc_now=lambda: datetime(2026, 11, 15, 12, 0),
        )
        if connected:
            self.accounts.save_connected(
                1, "student@gmail.com", "enc:access-1", "enc:refresh-1", datetime(2099, 1, 1),
                datetime(2026, 11, 14, 10, 0), datetime(2026, 11, 14, 10, 0),
            )

    def link_of(self, study_event_id):
        return next(link for link in self.links.list_links(1) if link.study_event_id == study_event_id)

    def with_data(self):
        self.schedules.add(
            1, None, FROM, TO, [lecture("A"), lecture("B", Weekday.WEDNESDAY), lecture("C", Weekday.FRIDAY)]
        )
        self.schedules.add(2, None, FROM, TO, [lecture("Svetimas")])  # another user's data must never be exported
        self.shifts.add(1, "Kavinė", date(2026, 11, 16), time(15, 0), time(19, 0))
        return self


def test_export_creates_one_google_event_per_record_and_records_the_run():
    world = World().with_data()

    result = world.service.export(1)

    assert (result.created, result.updated, result.deleted) == (4, 0, 0)
    assert len(world.provider.events) == 4  # 3 lectures + 1 shift, nothing of the other user (N-30)
    assert {b["summary"] for b in world.provider.events.values()} == {
        "A (paskaita)", "B (paskaita)", "C (paskaita)", "Darbas: Kavinė"}
    assert len(world.links.list_links(1)) == 4 and world.links.list_links(2) == []
    [operation] = world.operations.operations
    assert operation.operation_type.name == "EXPORT" and operation.status == SyncStatus.SUCCESS
    assert operation.created_count == 4
    assert operation.finished_at >= operation.started_at
    assert world.service.status(1).exported and world.service.status(1).last_success_at == operation.finished_at


def test_exporting_again_never_creates_duplicates():
    world = World().with_data()
    world.service.export(1)

    again = world.service.export(1)

    assert (again.created, again.updated, again.deleted) == (0, 0, 0)
    assert len(world.provider.events) == 4 and len(world.provider.calls_named("create_event")) == 4  # F-29


def test_a_changed_record_is_updated_in_place_and_a_removed_one_is_deleted_from_google():
    world = World().with_data()
    world.service.export(1)
    lecture_a, lecture_b = world.schedules.list_study_events(1)[:2]
    google_id_of_a = world.link_of(lecture_a.id).google_event_id

    world.schedules.update_event(1, lecture_a.id, replace(lecture_a, subject_name="A (pakeista)"))
    world.schedules.remove_event(1, lecture_b.id)
    world.links.unlink_study_event(lecture_b.id)  # what ON DELETE SET NULL does in the database
    result = world.service.export(1)

    assert (result.created, result.updated, result.deleted) == (0, 1, 1)
    assert world.provider.events[google_id_of_a]["summary"] == "A (pakeista) (paskaita)"
    assert len(world.provider.events) == 3 and len(world.links.list_links(1)) == 3
    assert [op.updated_count for op in world.operations.operations] == [0, 1]


def test_events_the_system_did_not_create_are_never_touched():
    world = World().with_data()
    world.provider.events["someone-elses-birthday"] = {"summary": "Gimtadienis"}
    world.service.export(1)
    removed = world.schedules.list_study_events(1)[0]
    world.schedules.remove_event(1, removed.id)
    world.links.unlink_study_event(removed.id)  # ON DELETE SET NULL

    result = world.service.export(1)

    assert result.deleted == 1  # only the event this system created
    assert world.provider.events["someone-elses-birthday"] == {"summary": "Gimtadienis"}
    assert ("delete_event", "someone-elses-birthday") not in world.provider.calls


def test_an_event_deleted_in_google_is_created_again_instead_of_failing():
    world = World().with_data()
    world.service.export(1)
    lecture_a = world.schedules.list_study_events(1)[0]
    link = world.link_of(lecture_a.id)
    del world.provider.events[link.google_event_id]  # the user removed it in Google Calendar
    world.schedules.update_event(1, lecture_a.id, lecture_a)

    result = world.service.export(1)

    assert (result.created, result.updated) == (1, 0) and len(world.provider.events) == 4
    assert world.link_of(lecture_a.id).google_event_id != link.google_event_id


def test_export_needs_a_connected_account():
    world = World(connected=False).with_data()
    with pytest.raises(CalendarError) as exc:
        world.service.export(1)
    assert exc.value.code == CalendarError.NOT_CONNECTED and world.provider.calls == []

    world = World().with_data()
    world.accounts.set_status(1, CalendarAccountStatus.RECONNECT_REQUIRED)
    with pytest.raises(CalendarError) as exc:
        world.service.export(1)
    assert exc.value.code == CalendarError.AUTH_EXPIRED and world.provider.calls == []


class FlakyProvider(fakes.FakeCalendarProvider):
    """Creates `succeed` events and then fails once with the given error."""

    def __init__(self, succeed, error):
        super().__init__()
        self.succeed, self.error = succeed, error

    def create_event(self, tokens, body):
        if self.succeed == 0 and self.error is not None:
            error, self.error = self.error, None
            raise error
        self.succeed -= 1
        return super().create_event(tokens, body)


def test_an_interrupted_export_keeps_what_was_done_and_the_rerun_creates_no_duplicates():
    world = World(FlakyProvider(2, CalendarError(CalendarError.UNAVAILABLE))).with_data()
    before = list(world.schedules.list_study_events(1))

    with pytest.raises(CalendarError) as exc:
        world.service.export(1)

    assert exc.value.code == CalendarError.UNAVAILABLE
    [failed] = world.operations.operations
    assert failed.status == SyncStatus.ERROR and failed.error_code == "UNAVAILABLE" and failed.created_count == 2
    assert len(world.links.list_links(1)) == 2 and world.schedules.list_study_events(1) == before  # local data intact
    assert world.accounts.get(1).status == CalendarAccountStatus.CONNECTED  # a network error is not a lost login

    rerun = world.service.export(1)  # N-32

    assert rerun.created == 2 and len(world.provider.events) == 4 and len(world.links.list_links(1)) == 4


def test_a_rejected_login_marks_the_account_as_needing_a_reconnect():
    world = World(fakes.FakeCalendarProvider(errors={
        "create_event": CalendarError(CalendarError.AUTH_EXPIRED), "refresh": CalendarError(CalendarError.AUTH_EXPIRED)
    })).with_data()

    with pytest.raises(CalendarError) as exc:
        world.service.export(1)

    assert exc.value.code == CalendarError.AUTH_EXPIRED
    assert world.accounts.get(1).status == CalendarAccountStatus.RECONNECT_REQUIRED  # N-33
    assert world.operations.operations[0].error_code == "AUTH_EXPIRED"


def test_tokens_that_cannot_be_decrypted_are_treated_as_expired():
    world = World().with_data()
    world.accounts.save_connected(1, "x@y.lt", "demo-not-a-real-token", "demo-not-a-real-token", None,
                                  datetime(2026, 11, 1), datetime(2026, 11, 1))

    with pytest.raises(CalendarError) as exc:
        world.service.export(1)

    assert exc.value.code == CalendarError.AUTH_EXPIRED
    assert world.accounts.get(1).status == CalendarAccountStatus.RECONNECT_REQUIRED and world.provider.events == {}


def test_an_expired_access_token_is_refreshed_once_and_the_new_one_is_stored_encrypted():
    world = World().with_data()
    world.accounts.save_connected(1, "x@y.lt", "enc:access-1", "enc:refresh-1", datetime(2026, 11, 15, 11, 0),  # past
                                  datetime(2026, 11, 1), datetime(2026, 11, 1))

    world.service.export(1)

    assert len(world.provider.calls_named("refresh")) == 1
    assert world.accounts.get(1).access_token_enc == "enc:access-2"
    assert world.accounts.get(1).token_expires_at.year == 2099
    assert {call[1] for call in world.provider.calls_named("create_event")} == {"access-2"}


def test_a_rejected_access_token_is_refreshed_and_the_request_repeated():
    class RejectsOldToken(fakes.FakeCalendarProvider):
        def create_event(self, tokens, body):
            if tokens.access_token == "access-1":
                raise CalendarError(CalendarError.AUTH_EXPIRED)
            return super().create_event(tokens, body)

    world = World(RejectsOldToken()).with_data()

    world.service.export(1)

    assert len(world.provider.events) == 4 and len(world.provider.calls_named("refresh")) == 1
    assert world.accounts.get(1).status == CalendarAccountStatus.CONNECTED


def test_an_unexpected_error_is_reported_as_unavailable_and_the_run_is_not_left_in_progress(caplog):
    class Broken(fakes.FakeCalendarProvider):
        def create_event(self, tokens, body):
            raise RuntimeError("secret detail: access-1")

    world = World(Broken()).with_data()
    with pytest.raises(CalendarError) as exc:
        world.service.export(1)

    assert exc.value.code == CalendarError.UNAVAILABLE
    assert world.operations.operations[0].status == SyncStatus.ERROR


def test_status_report_after_a_failed_run_shows_the_last_success_and_the_error():
    world = World().with_data()
    world.service.export(1)
    world.provider.errors["create_event"] = CalendarError(CalendarError.UNAVAILABLE)
    world.shifts.add(1, "Naujas darbas", date(2026, 11, 17), time(8, 0), time(9, 0))
    with pytest.raises(CalendarError):
        world.service.export(1)

    report = world.service.status(1)

    assert report.exported and report.last_error.error_code == "UNAVAILABLE"
    assert report.last_success_at == world.operations.operations[0].finished_at
    assert report.last_operation is report.last_error


def test_two_hundred_records_are_exported_in_a_single_run():
    world = World()
    world.schedules.add(1, None, FROM, TO, [lecture(f"Dalykas {i}", Weekday.MONDAY) for i in range(120)])
    for i in range(80):
        world.shifts.add(1, f"Darbas {i}", date(2026, 11, 16), time(8, 0), time(9, 0))

    result = world.service.export(1)

    assert result.created == 200 and len(world.provider.events) == 200 == len(world.links.list_links(1))


# ----------------------------------------------------------------------------- web

def client_for(world, user_id=1):
    client = create_app(services=Services(calendar=world.service)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def test_export_button_shows_how_many_records_were_exported_and_the_sync_statistics():
    world = World().with_data()
    client = client_for(world)

    page = client.post("/calendar/export", follow_redirects=True).get_data(as_text=True)

    assert "Eksportuota: 4 įrašų." in page
    assert "Eksportas" in page and "4 / 0 / 0" in page and "Sinchronizuota" in page
    assert "Eksportuoti į Google Calendar" in page


def test_export_without_a_connection_tells_the_user_to_connect_first():
    world = World(connected=False).with_data()
    page = client_for(world).post("/calendar/export", follow_redirects=True).get_data(as_text=True)
    assert "neprijungtas" in page.lower() and "Prijungti Google Calendar" in page


def test_a_failed_export_shows_the_reason_and_what_to_do():
    provider = fakes.FakeCalendarProvider(errors={"create_event": CalendarError(CalendarError.UNAVAILABLE)})
    world = World(provider).with_data()
    page = client_for(world).post("/calendar/export", follow_redirects=True).get_data(as_text=True)

    assert "Kalendoriaus tiekėjas nepasiekiamas. Bandykite dar kartą." in page
    assert "Paskutinė klaida" in page


def test_reconnect_is_requested_when_the_login_was_rejected():
    world = World(fakes.FakeCalendarProvider(errors={
        "create_event": CalendarError(CalendarError.AUTH_EXPIRED), "refresh": CalendarError(CalendarError.AUTH_EXPIRED)
    })).with_data()
    client = client_for(world)

    page = client.post("/calendar/export", follow_redirects=True).get_data(as_text=True)

    assert "Prisijunkite prie Google Calendar iš naujo." in page and "Reikia prisijungti iš naujo" in page
