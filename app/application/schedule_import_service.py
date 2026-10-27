"""Timetable import: upload, AI recognition, review and confirmation (F-03..F-08)."""

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Callable

from app.application.errors import RecognitionFailed, RowsValidationFailed, ValidationFailed
from app.application.ports import (
    AiRequestLog,
    PdfDocumentRepository,
    ScheduleRecognizer,
    ScheduleRepository,
)
from app.application.validation import (
    ChangeListener,
    format_time,
    ignore_changes,
    parse_time,
    validate_time_range,
)
from app.domain.entities import AiRequestType, PdfStatus, StudyEvent, StudyEventType
from app.domain.rules import MAX_PDF_SIZE_BYTES, SEMESTER_LENGTH_DAYS
from app.domain.weekday import Weekday


@dataclass(frozen=True)
class ReviewRow:
    """One editable row of the review table. All values are raw form strings."""

    subject: str
    event_type: str
    day_of_week: str
    start_time: str
    end_time: str
    room: str
    is_mandatory: bool

    @classmethod
    def from_event(cls, event: StudyEvent) -> "ReviewRow":
        return cls(
            subject=event.subject_name,
            event_type=event.event_type.value,
            day_of_week=event.weekday.value,
            start_time=format_time(event.start_time),
            end_time=format_time(event.end_time),
            room=event.room or "",
            is_mandatory=event.is_mandatory,
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecognizedUpload:
    pdf_document_id: int
    rows: list[ReviewRow]


class ScheduleImportService:
    def __init__(
        self,
        pdf_documents: PdfDocumentRepository,
        schedules: ScheduleRepository,
        recognizer: ScheduleRecognizer,
        ai_log: AiRequestLog,
        on_schedule_saved: ChangeListener = ignore_changes,
        today: Callable[[], date] = date.today,
    ):
        self._pdf_documents = pdf_documents
        self._schedules = schedules
        self._recognizer = recognizer
        self._ai_log = ai_log
        self._on_schedule_saved = on_schedule_saved
        self._today = today

    def upload_and_recognize(self, user_id: int, filename: str, content: bytes, consent_given: bool) -> RecognizedUpload:
        """Validate the file, run AI recognition and return rows for review.

        Raises ValidationFailed (field "file") or RecognitionFailed.
        """
        self._validate_upload(filename, content, consent_given)

        pdf_document = self._pdf_documents.add(user_id, filename)
        request_id = self._ai_log.start(user_id, AiRequestType.RECOGNITION, pdf_document.id)
        try:
            result = self._recognizer.recognize(content)
        except RecognitionFailed as exc:
            self._pdf_documents.set_status(pdf_document.id, PdfStatus.FAILED)
            self._ai_log.finish(request_id, exc.attempts, str(exc))
            raise

        self._pdf_documents.set_status(pdf_document.id, PdfStatus.RECOGNIZED)
        self._ai_log.finish(request_id, result.attempts, None)
        return RecognizedUpload(pdf_document.id, [ReviewRow.from_event(e) for e in result.events])

    def validate_rows(self, rows: list[ReviewRow]) -> list[dict[str, str]]:
        """One {field: error_code} dict per row; an empty dict means the row is valid."""
        return [self._validate_row(row) for row in rows]

    def confirm(self, user_id: int, pdf_document_id: int, rows: list[ReviewRow]) -> int:
        """Persist the schedule only after the user confirmed it (F-08, N-24)."""
        errors = self.validate_rows(rows)
        if any(errors):
            raise RowsValidationFailed(errors)

        today = self._today()
        schedule_id = self._schedules.add(
            user_id=user_id,
            pdf_document_id=pdf_document_id,
            valid_from=today,
            valid_to=today + timedelta(days=SEMESTER_LENGTH_DAYS),
            events=[self._to_event(row) for row in rows],
        )
        self._pdf_documents.set_status(pdf_document_id, PdfStatus.CONFIRMED)
        self._on_schedule_saved(user_id)
        return schedule_id

    def reject(self, pdf_document_id: int) -> None:
        """The user rejected the recognised data; nothing is saved."""
        self._pdf_documents.set_status(pdf_document_id, PdfStatus.FAILED)

    @staticmethod
    def _validate_upload(filename: str, content: bytes, consent_given: bool) -> None:
        if not filename.lower().endswith(".pdf"):
            raise ValidationFailed({"file": "not_pdf"})
        if len(content) > MAX_PDF_SIZE_BYTES:
            raise ValidationFailed({"file": "too_large"})
        if not consent_given:
            raise ValidationFailed({"file": "consent_required"})

    @staticmethod
    def _validate_row(row: ReviewRow) -> dict[str, str]:
        errors = validate_time_range(row.start_time, row.end_time)
        if not row.subject or not row.subject.strip():
            errors["subject"] = "required"
        if row.event_type not in {t.value for t in StudyEventType}:
            errors["event_type"] = "invalid_choice"
        if Weekday.from_code(row.day_of_week) is None:
            errors["day_of_week"] = "invalid_choice"
        return errors

    @staticmethod
    def _to_event(row: ReviewRow) -> StudyEvent:
        return StudyEvent(
            id=None,
            subject_name=row.subject.strip(),
            event_type=StudyEventType(row.event_type),
            weekday=Weekday(row.day_of_week),
            start_time=parse_time(row.start_time),
            end_time=parse_time(row.end_time),
            room=row.room.strip() or None,
            is_mandatory=row.is_mandatory,
        )
