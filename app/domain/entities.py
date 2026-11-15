"""Core entities and enums of the timetable domain.

Enum values are the codes stored in the database (defined by the specification).
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum

from app.domain.weekday import Weekday


class StudyEventType(Enum):
    LECTURE = "PASKAITA"
    PRACTICAL = "PRATYBOS"
    LABORATORY = "LABORATORINIS_DARBAS"


class WeekPattern(Enum):
    """On which study weeks an event takes place (see domain/academic_week.py)."""

    EVERY_WEEK = "KIEKVIENA"
    WEEK_1 = "PIRMA"
    WEEK_2 = "ANTRA"


class PdfStatus(Enum):
    UPLOADED = "IKELTAS"
    PROCESSING = "APDOROJAMAS"
    RECOGNIZED = "ATPAZINTAS"
    CONFIRMED = "PATVIRTINTAS"
    FAILED = "KLAIDA"


class CalendarAccountStatus(Enum):
    CONNECTED = "PRIJUNGTA"
    NOT_CONNECTED = "NEPRIJUNGTA"
    RECONNECT_REQUIRED = "REIKIA_PERPRISIJUNGTI"


class SyncOperationType(Enum):
    EXPORT = "EKSPORTAS"
    UPDATE = "ATNAUJINIMAS"


class SyncStatus(Enum):
    IN_PROGRESS = "VYKDOMAS"
    SUCCESS = "SEKMINGAS"
    ERROR = "KLAIDA"


class ReminderType(Enum):
    SEMESTER_START = "SEMESTRO_PRADZIA"
    MONTH_START = "MENESIO_PRADZIA"


class ConflictStatus(Enum):
    ACTIVE = "AKTYVUS"
    IGNORED = "IGNORUOTAS"
    RESOLVED = "ISSPRESTAS"


class NotificationType(Enum):
    CONFLICT = "KONFLIKTAS"
    SYSTEM_ERROR = "SISTEMOS_KLAIDA"
    REMINDER = "PRIMINIMAS"
    SYNC_ERROR = "SINCH_KLAIDA"


class AiRequestType(Enum):
    RECOGNITION = "ATPAZINIMAS"
    ANALYSIS = "ANALIZE"


@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str
    password_hash: str
    ai_consent: bool


@dataclass(frozen=True)
class PdfDocument:
    id: int
    user_id: int
    filename: str
    status: PdfStatus
    replace_existing: bool = False  # the new schedule is meant to replace the current one (F-22)


@dataclass(frozen=True)
class StudyEvent:
    """A lecture, practical or laboratory session. `id` is None until persisted."""

    id: int | None
    subject_name: str
    event_type: StudyEventType
    weekday: Weekday
    start_time: time
    end_time: time
    room: str | None
    is_mandatory: bool = True
    valid_from: date | None = None  # validity of the schedule the event belongs to (None = unknown / unlimited)
    valid_to: date | None = None
    week_pattern: WeekPattern = WeekPattern.EVERY_WEEK
    updated_at: datetime | None = None  # last manual change (used by the calendar sync)


@dataclass(frozen=True)
class WorkShift:
    """A working-time interval on a concrete date (F-09, F-18)."""

    id: int
    workplace_name: str
    work_date: date
    start_time: time
    end_time: time
    updated_at: datetime | None = None  # last manual change (used by the calendar sync)
    series_id: int | None = None  # the weekly series this shift belongs to
    is_exception: bool = False  # changed on its own: no longer follows its series

    @property
    def weekday(self) -> Weekday:
        return Weekday.of_date(self.work_date)

    @property
    def follows_series(self) -> bool:
        return self.series_id is not None and not self.is_exception


@dataclass(frozen=True)
class ShiftSeries:
    """A work shift that repeats every week from `first_date` to `last_date` (see db/migrations/011)."""

    id: int
    workplace_name: str
    start_time: time
    end_time: time
    first_date: date
    last_date: date
    updated_at: datetime | None = None


@dataclass(frozen=True)
class DetectedConflict:
    """Result of conflict analysis, before it is stored."""

    study_event_id: int
    work_shift_id: int
    overlap_minutes: int


@dataclass(frozen=True)
class Conflict:
    id: int
    study_event_id: int
    work_shift_id: int
    overlap_minutes: int


@dataclass(frozen=True)
class Notification:
    id: int
    message: str
    notification_type: NotificationType = NotificationType.CONFLICT


@dataclass(frozen=True)
class ReminderSetting:
    """A user's reminder preferences (F-21). `closed_period_start` is the period whose reminder was dismissed."""

    user_id: int
    enabled: bool = True
    closed_period_start: date | None = None


@dataclass(frozen=True)
class Reminder:
    """A reminder that should be shown now (F-20)."""

    period_start: date
    reminder_type: ReminderType
    text: str


@dataclass(frozen=True)
class CalendarTokens:
    """OAuth tokens in plain text. They live only in memory; the database holds them encrypted (N-43).

    `expires_at` is the access token's expiry in UTC (naive datetime).
    """

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    email: str | None = None


@dataclass(frozen=True)
class CalendarAccount:
    """The user's connected Google Calendar account (stored tokens are encrypted)."""

    user_id: int
    status: CalendarAccountStatus
    google_email: str | None = None
    access_token_enc: str | None = None
    refresh_token_enc: str | None = None
    token_expires_at: datetime | None = None  # UTC
    consent_given_at: datetime | None = None  # local time
    connected_at: datetime | None = None  # local time


@dataclass(frozen=True)
class CalendarEventLink:
    """Ties a study event or work shift to the Google event created for it (prevents duplicates, F-29).

    When the local record is deleted both ids become None: the Google event is then an orphan that the next
    synchronisation deletes. Only events with a stored link are ever changed or deleted (N-45).
    """

    id: int
    user_id: int
    study_event_id: int | None
    work_shift_id: int | None
    google_event_id: str
    synced_at: datetime  # local time
    shift_series_id: int | None = None

    @property
    def is_orphan(self) -> bool:
        return self.study_event_id is None and self.work_shift_id is None and self.shift_series_id is None


@dataclass(frozen=True)
class SyncOperation:
    """One export or update run and its result (F-27, F-30)."""

    id: int
    user_id: int
    operation_type: SyncOperationType
    status: SyncStatus
    started_at: datetime
    finished_at: datetime | None = None
    created_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
