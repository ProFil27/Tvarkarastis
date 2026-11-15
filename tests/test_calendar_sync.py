"""Updating Google Calendar after changes, errors and status (F-28, F-30, F-31, N-31..N-34, US-13, US-14)."""

from dataclasses import replace
from datetime import date, datetime, time

import pytest

from app.application.change_notifier import ChangeNotifier
from app.application.errors import CalendarError
from app.application.event_rows import ReviewRow
from app.application.study_event_service import StudyEventService
from app.application.work_shift_service import WorkShiftService
from app.container import Services
from app.domain.entities import CalendarAccountStatus, NotificationType, SyncOperationType, SyncStatus
from app.domain.weekday import Weekday
from app.web import create_app
from tests import fakes
from tests.test_calendar_export import World, lecture, FROM, TO

ROW = ReviewRow("Algoritmai", "PASKAITA", "KETVIRTADIENIS", "08:30", "10:00", "SRK-I-305", True)


def exported_world(provider=None):
    """A connected user who already exported a schedule; study events/shifts changes go through the real services."""
    world = World(provider).with_data()
    world.service.export(1)
    notifier = ChangeNotifier()
    world.events = StudyEventService(world.schedules, notifier, today=lambda: date(2026, 11, 14))
    world.work_shifts = WorkShiftService(world.shifts, notifier)
    notifier.subscribe(world.service.on_data_changed)
    return world


def sync_errors(world):
    return [n for n in world.notifications.list_unread(1) if n.notification_type == NotificationType.SYNC_ERROR]


# ----------------------------------------------------------------------------- manual "Sinchronizuoti dar kartą"

def test_sync_creates_new_records_updates_changed_ones_and_deletes_removed_ones_with_exact_counts():
    world = World().with_data()
    world.service.export(1)
    first, second = world.schedules.list_study_events(1)[:2]
    world.schedules.update_event(1, first.id, replace(first, room="Nauja salė"))  # changed
    world.schedules.remove_event(1, second.id)  # removed ...
    world.links.unlink_study_event(second.id)  # ... which the database turns into an orphan link
    world.schedules.add_event(1, replace(first, subject_name="Naujas dalykas"), FROM, TO)  # new
    world.shifts.add(1, "Kita darbovietė", date(2026, 11, 17), time(8, 0), time(9, 0))  # new

    result = world.service.sync(1)

    assert (result.created, result.updated, result.deleted) == (2, 1, 1)  # N-30: exact counts
    assert len(world.provider.events) == 5 == len(world.links.list_links(1))  # no duplicates, nothing stale
    operation = world.operations.last(1)
    assert operation.operation_type == SyncOperationType.UPDATE and operation.status == SyncStatus.SUCCESS
    assert (operation.created_count, operation.updated_count, operation.deleted_count) == (2, 1, 1)


def test_sync_without_changes_touches_nothing():
    world = World().with_data()
    world.service.export(1)
    calls_before = len(world.provider.calls)

    assert (world.service.sync(1).created, world.service.sync(1).updated, world.service.sync(1).deleted) == (0, 0, 0)
    assert len(world.provider.calls) == calls_before


def test_sync_needs_a_connection_and_an_earlier_export():
    world = World(connected=False).with_data()
    with pytest.raises(CalendarError) as exc:
        world.service.sync(1)
    assert exc.value.code == CalendarError.NOT_CONNECTED

    world = World().with_data()
    with pytest.raises(CalendarError) as exc:
        world.service.sync(1)
    assert exc.value.code == CalendarError.NOT_EXPORTED and world.provider.calls == []


# ----------------------------------------------------------------------------- automatic update after a change (F-28)

def test_editing_a_lecture_updates_exactly_that_google_event():
    world = exported_world()
    lecture_a = world.schedules.list_study_events(1)[0]
    google_id = next(l.google_event_id for l in world.links.list_links(1) if l.study_event_id == lecture_a.id)
    creates_before = len(world.provider.calls_named("create_event"))

    world.events.update_event(1, lecture_a.id, ReviewRow.from_event(replace(lecture_a, subject_name="Pakeistas")))

    assert world.provider.events[google_id]["summary"] == "Pakeistas (paskaita)"
    assert world.provider.calls_named("update_event") == [("update_event", google_id)]  # the others are untouched
    assert len(world.provider.calls_named("create_event")) == creates_before and len(world.provider.events) == 4


def test_adding_a_lecture_and_changing_or_removing_a_shift_are_reflected_in_google():
    world = exported_world()

    world.events.add_event(1, ROW)
    assert len(world.provider.events) == 5

    shift = world.shifts.list_for_user(1)[0]
    world.work_shifts.update_shift(1, shift.id, "Naujas darbdavys", "2026-11-18", "09:00", "11:00")
    changed = next(b for b in world.provider.events.values() if b["summary"] == "Darbas: Naujas darbdavys")
    assert changed["start"]["dateTime"] == "2026-11-18T09:00:00"

    world.shifts.remove(1, shift.id)
    world.links.unlink_work_shift(shift.id)
    world.work_shifts.remove_shift(1, 99999)  # a no-op removal changes nothing and so triggers no update
    world.service.on_data_changed(1)
    assert len(world.provider.events) == 4 and all(b["summary"] != "Darbas: Naujas darbdavys" for b in world.provider.events.values())


def test_no_update_without_a_connection_or_an_export_and_no_error_either():
    for world in (World(connected=False).with_data(), World().with_data()):
        world.service.on_data_changed(1)
        assert world.provider.calls == [] and sync_errors(world) == []

    world = exported_world()
    world.accounts.set_status(1, CalendarAccountStatus.RECONNECT_REQUIRED)
    calls = len(world.provider.calls)
    world.service.on_data_changed(1)
    assert len(world.provider.calls) == calls  # nothing is attempted while the login is lost


# ----------------------------------------------------------------------------- errors (F-31, N-33, N-34)

def test_a_calendar_outage_does_not_undo_the_edit_and_the_user_is_told():
    world = exported_world()
    world.provider.errors["update_event"] = CalendarError(CalendarError.UNAVAILABLE)
    lecture_a = world.schedules.list_study_events(1)[0]

    saved = world.events.update_event(1, lecture_a.id, ReviewRow.from_event(replace(lecture_a, subject_name="Pakeistas")))

    assert saved.subject_name == "Pakeistas" == world.schedules.get_event(1, lecture_a.id).subject_name  # local data stays
    [notice] = sync_errors(world)
    assert notice.message == "Kalendoriaus sinchronizavimas nepavyko. Kalendoriaus tiekėjas nepasiekiamas. Bandykite dar kartą."
    last = world.operations.last(1)
    assert last.status == SyncStatus.ERROR and last.error_code == "UNAVAILABLE"
    assert world.accounts.get(1).status == CalendarAccountStatus.CONNECTED


def test_the_same_problem_is_notified_only_once_until_it_is_dismissed():
    world = exported_world()
    world.provider.errors["update_event"] = CalendarError(CalendarError.UNAVAILABLE)
    lecture_a = world.schedules.list_study_events(1)[0]
    for name in ("A1", "A2", "A3"):
        world.events.update_event(1, lecture_a.id, ReviewRow.from_event(replace(lecture_a, subject_name=name)))

    assert len(sync_errors(world)) == 1

    world.notifications.mark_read(1, sync_errors(world)[0].id)
    world.events.update_event(1, lecture_a.id, ReviewRow.from_event(replace(lecture_a, subject_name="A4")))
    assert len(sync_errors(world)) == 1  # a new notification after the old one was dismissed


def test_the_change_is_synchronised_later_when_the_calendar_is_back():
    world = exported_world()
    world.provider.errors["update_event"] = CalendarError(CalendarError.UNAVAILABLE)
    lecture_a = world.schedules.list_study_events(1)[0]
    world.events.update_event(1, lecture_a.id, ReviewRow.from_event(replace(lecture_a, subject_name="Vėliau")))
    google_id = next(l.google_event_id for l in world.links.list_links(1) if l.study_event_id == lecture_a.id)
    assert world.provider.events[google_id]["summary"] == "A (paskaita)"  # Google still has the old value

    del world.provider.errors["update_event"]
    result = world.service.sync(1)  # "Sinchronizuoti dar kartą"

    assert result.updated == 1 and world.provider.events[google_id]["summary"] == "Vėliau (paskaita)"


def test_a_lost_login_asks_the_user_to_connect_again_and_stops_further_attempts():
    world = exported_world(fakes.FakeCalendarProvider(errors={}))
    world.provider.errors.update({"update_event": CalendarError(CalendarError.AUTH_EXPIRED),
                                  "refresh": CalendarError(CalendarError.AUTH_EXPIRED)})
    lecture_a = world.schedules.list_study_events(1)[0]

    world.events.update_event(1, lecture_a.id, ReviewRow.from_event(replace(lecture_a, subject_name="X")))

    assert world.accounts.get(1).status == CalendarAccountStatus.RECONNECT_REQUIRED  # N-33
    assert sync_errors(world)[0].message.endswith("Prisijunkite prie Google Calendar iš naujo.")
    with pytest.raises(CalendarError) as exc:
        world.service.sync(1)
    assert exc.value.code == CalendarError.AUTH_EXPIRED


def test_a_failing_calendar_listener_cannot_block_the_conflict_check():
    class Broken(fakes.FakeCalendarProvider):
        def update_event(self, tokens, google_event_id, body):
            raise RuntimeError("boom")

    world = exported_world(Broken())
    seen = []
    notifier = ChangeNotifier()
    notifier.subscribe(world.service.on_data_changed)
    notifier.subscribe(seen.append)  # e.g. the conflict check
    lecture_a = world.schedules.list_study_events(1)[0]
    world.schedules.update_event(1, lecture_a.id, replace(lecture_a, subject_name="Y"))

    notifier(1)

    assert seen == [1]


# ----------------------------------------------------------------------------- web

def client_for(world):
    client = create_app(services=Services(calendar=world.service)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1
    return client


def test_sync_button_reports_the_counts():
    world = World().with_data()
    world.service.export(1)
    lecture_a = world.schedules.list_study_events(1)[0]
    world.schedules.update_event(1, lecture_a.id, replace(lecture_a, room="Kita"))

    page = client_for(world).post("/calendar/sync", follow_redirects=True).get_data(as_text=True)

    assert "Sinchronizuota: sukurta 0, atnaujinta 1, ištrinta 0." in page
    assert "Atnaujinimas" in page and "0 / 1 / 0" in page and "Sinchronizuoti dar kartą" in page


def test_sync_button_before_the_first_export_explains_what_to_do():
    page = client_for(World().with_data()).post("/calendar/sync", follow_redirects=True).get_data(as_text=True)
    assert "Pirmiausia eksportuokite jį į Google Calendar." in page


def test_status_shows_the_last_successful_sync_time_and_the_last_error_in_the_expected_format():
    world = World().with_data()
    world.service.export(1)
    world.provider.errors["create_event"] = CalendarError(CalendarError.UNAVAILABLE)
    world.shifts.add(1, "Naujas", date(2026, 11, 20), time(8, 0), time(9, 0))
    with pytest.raises(CalendarError):
        world.service.sync(1)

    page = client_for(world).get("/calendar/").get_data(as_text=True)

    success = world.operations.last_success(1).finished_at.strftime("%Y-%m-%d %H:%M")
    assert success in page  # YYYY-MM-DD HH:MM (N-29)
    assert "Paskutinė klaida" in page and "Kalendoriaus tiekėjas nepasiekiamas. Bandykite dar kartą." in page
