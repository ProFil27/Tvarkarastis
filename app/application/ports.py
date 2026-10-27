"""Ports: the interfaces the application layer needs from the outside world.

Infrastructure implements them (Postgres repositories, AI agents, password
hashing). Services depend only on these protocols, so storage or the AI provider
can be replaced without touching business logic (N-18, N-19).
"""

from dataclasses import dataclass
from datetime import date, time
from typing import Protocol

from app.domain.entities import (
    AiRequestType,
    Conflict,
    DetectedConflict,
    Notification,
    PdfDocument,
    PdfStatus,
    StudyEvent,
    User,
    WorkShift,
)
from app.domain.weekday import Weekday


@dataclass(frozen=True)
class RecognitionResult:
    events: list[StudyEvent]
    attempts: int


@dataclass(frozen=True)
class AnalysisResult:
    conflicts: list[DetectedConflict]
    attempts: int


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


class UserRepository(Protocol):
    def add(self, name: str, email: str, password_hash: str, ai_consent: bool) -> User: ...

    def get_by_email(self, email: str) -> User | None: ...


class PdfDocumentRepository(Protocol):
    def add(self, user_id: int, filename: str) -> PdfDocument: ...

    def set_status(self, pdf_document_id: int, status: PdfStatus) -> None: ...


class ScheduleRepository(Protocol):
    def add(
        self, user_id: int, pdf_document_id: int | None, valid_from: date, valid_to: date, events: list[StudyEvent]
    ) -> int: ...

    def list_study_events(
        self, user_id: int, week_start: date | None = None, week_end: date | None = None
    ) -> list[StudyEvent]:
        """All study events of the user; if a week is given, only schedules valid in that week."""
        ...


class WorkShiftRepository(Protocol):
    def add(
        self, user_id: int, workplace_name: str, weekday: Weekday, start_time: time, end_time: time
    ) -> WorkShift: ...

    def list_for_user(self, user_id: int) -> list[WorkShift]: ...

    def remove(self, user_id: int, shift_id: int) -> bool:
        """Remove the shift only if it belongs to the user (N-21)."""
        ...


class ConflictRepository(Protocol):
    def list_active(self, user_id: int) -> list[Conflict]: ...

    def replace_active(self, user_id: int, detected: list[DetectedConflict]) -> list[Conflict]:
        """Synchronise active conflicts with `detected`; return only the newly created ones."""
        ...


class NotificationRepository(Protocol):
    def add(self, user_id: int, conflict_id: int | None, message: str) -> None: ...

    def list_unread(self, user_id: int) -> list[Notification]: ...

    def mark_read(self, user_id: int, notification_id: int) -> bool: ...


class AiRequestLog(Protocol):
    def start(self, user_id: int, request_type: AiRequestType, pdf_document_id: int | None = None) -> int: ...

    def finish(self, ai_request_id: int, attempts: int, error: str | None) -> None: ...


class ScheduleRecognizer(Protocol):
    def recognize(self, pdf_content: bytes) -> RecognitionResult:
        """Read a timetable PDF. Raises RecognitionFailed."""
        ...


class ConflictAnalyzer(Protocol):
    def analyze(self, events: list[StudyEvent], shifts: list[WorkShift]) -> AnalysisResult:
        """Find overlaps between events and shifts. Raises AnalysisFailed."""
        ...
