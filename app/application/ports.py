"""Ports: the interfaces the application layer needs from the outside world.

Infrastructure implements them (Postgres repositories, AI agents, password
hashing). Services depend only on these protocols, so storage or the AI provider
can be replaced without touching business logic (N-18, N-19).
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Protocol

from app.domain.entities import (
    AiRequestType,
    CalendarAccount,
    CalendarAccountStatus,
    CalendarEventLink,
    CalendarTokens,
    Conflict,
    DetectedConflict,
    Notification,
    NotificationType,
    PdfDocument,
    PdfStatus,
    ReminderSetting,
    ReminderType,
    StudyEvent,
    SyncOperation,
    SyncOperationType,
    SyncStatus,
    User,
    WorkShift,
)


@dataclass(frozen=True)
class RecognitionResult:
    events: list[StudyEvent]
    attempts: int
    valid_from: date | None = None  # validity period read from the PDF (None = not found)
    valid_to: date | None = None


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
    def add(self, user_id: int, filename: str, replace_existing: bool = False) -> PdfDocument: ...

    def get(self, pdf_document_id: int) -> PdfDocument | None: ...

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

    def count_events(self, user_id: int) -> int:
        """Number of study events in all of the user's schedules."""
        ...

    def replace_all(
        self, user_id: int, pdf_document_id: int | None, valid_from: date, valid_to: date, events: list[StudyEvent]
    ) -> int:
        """In one transaction: remove all of the user's schedules and save the new one (F-23, DPK-10)."""
        ...

    def last_schedule_date(self, user_id: int) -> date | None:
        """Date on which the user last saved a schedule (None if never)."""
        ...

    def get_event(self, user_id: int, event_id: int) -> StudyEvent | None:
        """The event only if it belongs to the user (N-21)."""
        ...

    def add_event(self, user_id: int, event: StudyEvent, default_from: date, default_to: date) -> StudyEvent:
        """Add an event to the user's latest schedule; create a schedule valid default_from..default_to if none."""
        ...

    def update_event(self, user_id: int, event_id: int, event: StudyEvent) -> StudyEvent | None:
        """Replace all editable fields of the user's event and set its change time; None if it is not theirs."""
        ...

    def remove_event(self, user_id: int, event_id: int) -> bool:
        """Remove the event only if it belongs to the user."""
        ...


class WorkShiftRepository(Protocol):
    def add(
        self, user_id: int, workplace_name: str, work_date: date, start_time: time, end_time: time
    ) -> WorkShift: ...

    def list_for_user(self, user_id: int) -> list[WorkShift]: ...

    def get(self, user_id: int, shift_id: int) -> WorkShift | None:
        """The shift only if it belongs to the user (N-21)."""
        ...

    def update(
        self, user_id: int, shift_id: int, workplace_name: str, work_date: date, start_time: time, end_time: time
    ) -> WorkShift | None:
        """Change the user's shift and set its change time; None if it is not theirs."""
        ...

    def remove(self, user_id: int, shift_id: int) -> bool:
        """Remove the shift only if it belongs to the user (N-21)."""
        ...


class ReminderSettingRepository(Protocol):
    def get(self, user_id: int) -> ReminderSetting:
        """The user's settings; reminders are enabled by default."""
        ...

    def set_enabled(self, user_id: int, enabled: bool) -> None: ...

    def set_closed_period(self, user_id: int, period_start: date, reminder_type: ReminderType) -> None: ...


class ConflictRepository(Protocol):
    def list_active(self, user_id: int) -> list[Conflict]: ...

    def replace_active(self, user_id: int, detected: list[DetectedConflict]) -> list[Conflict]:
        """Synchronise active conflicts with `detected`; return only the newly created ones.

        Active conflicts that are no longer detected are marked resolved (KVK-7), not deleted.
        """
        ...


class NotificationRepository(Protocol):
    def add(
        self,
        user_id: int,
        conflict_id: int | None,
        message: str,
        notification_type: NotificationType = NotificationType.CONFLICT,
    ) -> None: ...

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


@dataclass(frozen=True)
class AuthorizationRequest:
    """Where to send the user to approve access, and the PKCE verifier needed to finish the sign-in."""

    url: str
    code_verifier: str


class TokenCipher(Protocol):
    def encrypt(self, plain_text: str) -> str:
        """Raises CalendarError(NOT_CONFIGURED) if no encryption key is configured."""
        ...

    def decrypt(self, cipher_text: str) -> str:
        """Raises CalendarError(AUTH_EXPIRED) if the text cannot be decrypted (wrong key / damaged)."""
        ...

    @property
    def available(self) -> bool: ...


class CalendarAccountRepository(Protocol):
    def get(self, user_id: int) -> CalendarAccount | None: ...

    def save_connected(
        self,
        user_id: int,
        google_email: str | None,
        access_token_enc: str,
        refresh_token_enc: str | None,
        token_expires_at: datetime | None,
        consent_given_at: datetime,
        connected_at: datetime,
    ) -> CalendarAccount: ...

    def update_tokens(
        self, user_id: int, access_token_enc: str, refresh_token_enc: str | None, token_expires_at: datetime | None
    ) -> None: ...

    def set_status(self, user_id: int, status: CalendarAccountStatus) -> None: ...


class CalendarProvider(Protocol):
    """The calendar service (IGoogleCalendar). Only the adapter for that service implements it (N-41, N-42)."""

    def is_configured(self) -> bool: ...

    def authorization_url(self, state: str) -> AuthorizationRequest: ...

    def exchange_code(self, code: str, code_verifier: str) -> CalendarTokens:
        """Raises CalendarError (INVALID_CODE, UNAVAILABLE)."""
        ...

    def refresh(self, tokens: CalendarTokens) -> CalendarTokens:
        """Raises CalendarError (AUTH_EXPIRED when the refresh token no longer works, UNAVAILABLE)."""
        ...

    def create_event(self, tokens: CalendarTokens, body: dict) -> str:
        """Create an event from a Google Calendar `Event` resource (JSON); returns its Google id.

        Retries network errors, HTTP 5xx and 429 after 1, 2 and 4 seconds (N-31), then raises
        CalendarError(UNAVAILABLE). Other errors: AUTH_EXPIRED, REJECTED.
        """
        ...

    def update_event(self, tokens: CalendarTokens, google_event_id: str, body: dict) -> None:
        """Replace an event. Raises CalendarError (NOT_FOUND if it no longer exists, plus those of create_event)."""
        ...

    def delete_event(self, tokens: CalendarTokens, google_event_id: str) -> None:
        """Delete an event; an event that is already gone counts as deleted."""
        ...


class CalendarEventRepository(Protocol):
    def list_links(self, user_id: int) -> list[CalendarEventLink]: ...

    def add_link(
        self,
        user_id: int,
        study_event_id: int | None,
        work_shift_id: int | None,
        google_event_id: str,
        synced_at: datetime,
    ) -> CalendarEventLink: ...

    def touch_link(self, link_id: int, synced_at: datetime) -> None: ...

    def replace_google_event(self, link_id: int, google_event_id: str, synced_at: datetime) -> None:
        """Point an existing link at a newly created Google event."""
        ...

    def remove_link(self, link_id: int) -> None: ...


class SyncOperationRepository(Protocol):
    def start(self, user_id: int, operation_type: SyncOperationType, started_at: datetime) -> int: ...

    def finish(
        self,
        operation_id: int,
        status: SyncStatus,
        finished_at: datetime,
        created: int,
        updated: int,
        deleted: int,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None: ...

    def last(self, user_id: int) -> SyncOperation | None:
        """The most recent finished operation (successful or not)."""
        ...

    def last_success(self, user_id: int) -> SyncOperation | None: ...

    def has_export(self, user_id: int) -> bool:
        """Whether a successful export was made (updates only make sense after one)."""
        ...
