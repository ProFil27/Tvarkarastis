"""Runs slow follow-up work (the Google Calendar update) after a change without making the user wait."""

import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)


def start_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True).start()


def run_inline(work: Callable[[], None]) -> None:
    work()


class CoalescingRunner:
    """Runs `job(user_id)` for a user, one run at a time.

    A request that arrives while a run is in progress is not run in parallel: it only marks the user as
    "changed again", and the running worker repeats the job once more when it finishes. Many quick edits
    therefore produce one extra run instead of one run each, and two runs for a user never overlap.
    """

    def __init__(self, job: Callable[[int], None], spawn: Callable[[Callable[[], None]], None] = run_inline):
        self._job = job
        self._spawn = spawn
        self._lock = threading.Lock()
        self._running: set[int] = set()
        self._again: set[int] = set()

    def request(self, user_id: int) -> None:
        with self._lock:
            if user_id in self._running:
                self._again.add(user_id)
                return
            self._running.add(user_id)
        self._spawn(lambda: self._work(user_id))

    def is_busy(self, user_id: int) -> bool:
        with self._lock:
            return user_id in self._running

    def _work(self, user_id: int) -> None:
        while True:
            try:
                self._job(user_id)
            except Exception:  # noqa: BLE001 - a failing job must not kill the worker or leave the user "busy"
                log.exception("Background job failed")
            with self._lock:
                if user_id in self._again:
                    self._again.discard(user_id)
                    continue
                self._running.discard(user_id)
                return
