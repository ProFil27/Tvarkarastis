"""Conflict detection between study events and work shifts (F-12..F-16)."""

import logging

from app.application.errors import AnalysisFailed
from app.application.ports import (
    AiRequestLog,
    ConflictAnalyzer,
    ConflictRepository,
    NotificationRepository,
    ScheduleRepository,
    WorkShiftRepository,
)
from app.application.validation import format_time
from app.domain.entities import AiRequestType, DetectedConflict, StudyEvent, WorkShift
from app.domain.overlap import overlap_minutes

log = logging.getLogger(__name__)


class ConflictService:
    def __init__(
        self,
        schedules: ScheduleRepository,
        shifts: WorkShiftRepository,
        conflicts: ConflictRepository,
        notifications: NotificationRepository,
        analyzer: ConflictAnalyzer,
        ai_log: AiRequestLog,
    ):
        self._schedules = schedules
        self._shifts = shifts
        self._conflicts = conflicts
        self._notifications = notifications
        self._analyzer = analyzer
        self._ai_log = ai_log

    def run_check(self, user_id: int) -> None:
        """Detect conflicts for a user and create notifications for new ones.

        Never raises into the caller (N-11): on failure the problem is logged and
        previously stored conflicts stay unchanged.
        """
        events = self._schedules.list_study_events(user_id)
        shifts = self._shifts.list_for_user(user_id)
        request_id = self._ai_log.start(user_id, AiRequestType.ANALYSIS)

        try:
            result = self._analyzer.analyze(events, shifts)
        except AnalysisFailed as exc:
            log.warning("Conflict check failed: %s", exc)
            self._ai_log.finish(request_id, exc.attempts, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - the caller must never see analyzer failures
            log.exception("Unexpected conflict check error")
            self._ai_log.finish(request_id, 0, str(exc))
            return

        self._ai_log.finish(request_id, result.attempts, None)
        verified = self._verify(result.conflicts, events, shifts)

        events_by_id = {e.id: e for e in events}
        for conflict in self._conflicts.replace_active(user_id, verified):
            event = events_by_id[conflict.study_event_id]
            self._notifications.add(user_id, conflict.id, _notification_text(event))

    @staticmethod
    def _verify(
        detected: list[DetectedConflict], events: list[StudyEvent], shifts: list[WorkShift]
    ) -> list[DetectedConflict]:
        """Keep only conflicts the domain rule confirms, with recomputed durations (N-09)."""
        events_by_id = {e.id: e for e in events}
        shifts_by_id = {s.id: s for s in shifts}
        verified: dict[tuple[int, int], DetectedConflict] = {}
        for item in detected:
            event = events_by_id.get(item.study_event_id)
            shift = shifts_by_id.get(item.work_shift_id)
            if event is None or shift is None:
                continue
            minutes = overlap_minutes(event, shift)
            if minutes > 0:
                verified[(event.id, shift.id)] = DetectedConflict(event.id, shift.id, minutes)
        return list(verified.values())


def _notification_text(event: StudyEvent) -> str:
    """User-facing text (F-16), in Lithuanian."""
    return "Aptiktas konfliktas: {} {}–{}".format(
        event.weekday.label.lower(), format_time(event.start_time), format_time(event.end_time)
    )
