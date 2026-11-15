"""The calendar update after a change runs in the background without blocking the user or overlapping itself."""

import threading
from datetime import datetime

from app.application.background import CoalescingRunner
from app.application.calendar_sync_service import CalendarSyncService
from tests import fakes
from tests.test_calendar_export import World


def test_requests_during_a_run_are_merged_into_one_more_run():
    runs, queued = [], []
    runner = CoalescingRunner(lambda user_id: runs.append(user_id), spawn=queued.append)

    runner.request(1)
    runner.request(1)  # while the first run is still "starting"
    runner.request(1)
    assert runner.is_busy(1) and runs == []

    queued.pop()()  # the worker starts

    assert runs == [1, 1]  # the first run plus exactly one repeat for the merged requests
    assert not runner.is_busy(1)


def test_users_are_independent_and_a_failing_job_does_not_leave_the_user_busy():
    calls = []

    def job(user_id):
        calls.append(user_id)
        if user_id == 1:
            raise RuntimeError("boom")

    runner = CoalescingRunner(job)  # inline
    runner.request(1)
    runner.request(2)

    assert calls == [1, 2] and not runner.is_busy(1) and not runner.is_busy(2)


def test_a_change_returns_immediately_while_google_is_still_being_updated():
    class SlowProvider(fakes.FakeCalendarProvider):
        def __init__(self):
            super().__init__()
            self.release = threading.Event()
            self.started = threading.Event()

        def update_event(self, tokens, google_event_id, body):
            self.started.set()
            assert self.release.wait(5)
            return super().update_event(tokens, google_event_id, body)

    world = World(SlowProvider()).with_data()
    world.service.export(1)
    background = CalendarSyncService(
        world.provider, world.accounts, world.cipher, world.links, world.operations, world.schedules, world.shifts,
        world.series, world.notifications, now=datetime.now, utc_now=lambda: datetime(2026, 11, 15, 12, 0),
        background=True,
    )
    lecture = world.schedules.list_study_events(1)[0]
    world.schedules.update_event(1, lecture.id, lecture)  # a changed record

    background.on_data_changed(1)  # must not wait for Google

    assert world.provider.started.wait(5) and background.status(1).syncing is True
    world.provider.release.set()
    for _ in range(100):
        if not background.status(1).syncing:
            break
        threading.Event().wait(0.05)
    assert background.status(1).syncing is False
    assert world.operations.last(1).updated_count == 1
