"""Tiny publish/subscribe hook used to react to data changes without coupling features.

Schedule import and work shifts call the notifier after they change a user's data
(F-12); the conflict feature subscribes to it. Features stay independent: none of
them imports another one.
"""

from typing import Callable


class ChangeNotifier:
    def __init__(self) -> None:
        self._listeners: list[Callable[[int], None]] = []

    def subscribe(self, listener: Callable[[int], None]) -> None:
        self._listeners.append(listener)

    def __call__(self, user_id: int) -> None:
        for listener in self._listeners:
            listener(user_id)
