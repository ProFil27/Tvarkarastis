"""Independent calendar requests of one run are sent side by side (N-35) without losing track of what was created."""

import threading
import time
from datetime import date, datetime, time as clock_time
from time import sleep

import pytest

from app.application.calendar_sync_service import CalendarSyncService
from app.application.errors import CalendarError
from app.domain.entities import SyncStatus
from tests import fakes
from tests.test_calendar_export import World


class SlowThreadSafeProvider(fakes.FakeCalendarProvider):
    """Every request takes 50 ms; counts how many run at the same time."""

    def __init__(self, fail_on=None):
        super().__init__()
        self.lock = threading.Lock()
        self.running = self.peak = 0
        self.fail_on = fail_on or set()

    def create_event(self, tokens, body):
        with self.lock:
            self.running += 1
            self.peak = max(self.peak, self.running)
            number = self._next_event + 1
            self._next_event = number
        try:
            sleep(0.05)
            if number in self.fail_on:
                raise CalendarError(CalendarError.UNAVAILABLE)
            with self.lock:
                self.events[f"g{number}"] = body
            return f"g{number}"
        finally:
            with self.lock:
                self.running -= 1


def parallel_world(provider, shifts=40, workers=8):
    world = World(provider)
    for i in range(shifts):
        world.shifts.add(1, f"Darbas {i}", date(2026, 11, 16), clock_time(8, 0), clock_time(9, 0))
    world.service = CalendarSyncService(
        world.provider, world.accounts, world.cipher, world.links, world.operations, world.schedules, world.shifts,
        world.series, world.notifications, now=datetime.now, utc_now=lambda: datetime(2026, 11, 15, 12, 0),
        workers=workers,
    )
    return world


def test_requests_run_side_by_side_and_every_event_gets_its_link():
    provider = SlowThreadSafeProvider()
    world = parallel_world(provider)

    started = time.perf_counter()
    result = world.service.export(1)
    elapsed = time.perf_counter() - started

    assert result.created == 40 and len(provider.events) == 40 == len(world.links.list_links(1))
    assert provider.peak > 1  # more than one request was in flight at once
    assert elapsed < 40 * 0.05 / 2  # clearly faster than sending them one after another (2 s)
    assert len({link.google_event_id for link in world.links.list_links(1)}) == 40


def test_one_failing_request_does_not_lose_the_links_of_the_others_and_the_rerun_finishes_the_job():
    provider = SlowThreadSafeProvider(fail_on={7})
    world = parallel_world(provider, shifts=20)

    with pytest.raises(CalendarError):
        world.service.export(1)

    assert len(provider.events) == 19 and len(world.links.list_links(1)) == 19  # all 19 successes are recorded
    failed = world.operations.last(1)
    assert failed.status == SyncStatus.ERROR and failed.created_count == 19

    provider.fail_on.clear()
    rerun = world.service.export(1)

    assert rerun.created == 1 and len(provider.events) == 20 == len(world.links.list_links(1))  # no duplicates


def test_a_single_worker_sends_in_turn_and_stops_at_the_first_error():
    provider = SlowThreadSafeProvider(fail_on={3})
    world = parallel_world(provider, shifts=10, workers=1)

    with pytest.raises(CalendarError):
        world.service.export(1)

    assert provider.peak == 1 and len(world.links.list_links(1)) == 2
