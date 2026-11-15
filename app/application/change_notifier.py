"""Tiny publish/subscribe hook used to react to data changes without coupling features.

Schedule import, lectures and work shifts call the notifier after they change a user's data
(F-12, F-19); the conflict check and the calendar sync subscribe to it. Features stay independent:
none of them imports another one.
"""

import logging
from typing import Callable

log = logging.getLogger(__name__)


class ChangeNotifier:
    def __init__(self) -> None:
        self._listeners: list[Callable[[int], None]] = []

    def subscribe(self, listener: Callable[[int], None]) -> None:
        self._listeners.append(listener)

    def __call__(self, user_id: int) -> None:
        """Run every listener. A failing listener is logged and never blocks the others or the saved change."""
        for listener in self._listeners:
            try:
                listener(user_id)
            except Exception:  # noqa: BLE001 - N-34: a saved edit must survive any follow-up failure
                log.exception("Change listener %r failed", listener)
