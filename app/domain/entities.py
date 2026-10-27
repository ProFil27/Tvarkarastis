"""Core entities and enums of the timetable domain.

Enum values are the codes stored in the database (defined by the specification).
"""

from dataclasses import dataclass
from datetime import time
from enum import Enum

from app.domain.weekday import Weekday


class StudyEventType(Enum):
    LECTURE = "PASKAITA"
    PRACTICAL = "PRATYBOS"
    LABORATORY = "LABORATORINIS_DARBAS"


class PdfStatus(Enum):
    UPLOADED = "IKELTAS"
    PROCESSING = "APDOROJAMAS"
    RECOGNIZED = "ATPAZINTAS"
    CONFIRMED = "PATVIRTINTAS"
    FAILED = "KLAIDA"


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


@dataclass(frozen=True)
class WorkShift:
    id: int
    workplace_name: str
    weekday: Weekday
    start_time: time
    end_time: time


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
