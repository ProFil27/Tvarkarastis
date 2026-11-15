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
    parse_date,
    parse_time,
    validate_time_range,
)
from app.domain.entities import AiRequestType, PdfStatus, StudyEvent, StudyEventType, WeekPattern
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
    week_pattern: str = WeekPattern.EVERY_WEEK.value

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
            week_pattern=event.week_pattern.value,
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecognizedUpload:
    pdf_document_id: int
    rows: list[ReviewRow]
    valid_from: str = ""  # "YYYY-MM-DD" read from the PDF, "" if it was not found
    valid_to: str = ""


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

    def upload_and_recognize(
        self, user_id: int, filename: str, content: bytes, consent_given: bool
    ) -> RecognizedUpload:
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
        return RecognizedUpload(
            pdf_document.id,
            [ReviewRow.from_event(e) for e in result.events],
            result.valid_from.isoformat() if result.valid_from else "",
            result.valid_to.isoformat() if result.valid_to else "",
        )

    def validate_rows(self, rows: list[ReviewRow]) -> list[dict[str, str]]:
        """One {field: error_code} dict per row; an empty dict means the row is valid."""
        return [self._validate_row(row) for row in rows]

    def confirm(
        self, user_id: int, pdf_document_id: int, rows: list[ReviewRow], valid_from: str = "", valid_to: str = ""
    ) -> int:
        """Persist the schedule only after the user confirmed it (F-08, N-24).

        `valid_from` / `valid_to` ("YYYY-MM-DD") are the schedule's validity period; when both are empty
        the schedule is valid from today for one semester.
        """
        errors = self.validate_rows(rows)
        if any(errors):
            raise RowsValidationFailed(errors)
        period_errors = self.validate_period(valid_from, valid_to)
        if period_errors:
            raise ValidationFailed(period_errors)

        if valid_from or valid_to:
            period = (parse_date(valid_from), parse_date(valid_to))
        else:
            today = self._today()
            period = (today, today + timedelta(days=SEMESTER_LENGTH_DAYS))
        schedule_id = self._schedules.add(
            user_id=user_id,
            pdf_document_id=pdf_document_id,
            valid_from=period[0],
            valid_to=period[1],
            events=[self._to_event(row) for row in rows],
        )
        self._pdf_documents.set_status(pdf_document_id, PdfStatus.CONFIRMED)
        self._on_schedule_saved(user_id)
        return schedule_id

    @staticmethod
    def validate_period(valid_from: str, valid_to: str) -> dict[str, str]:
        """Both dates empty (default period) or both valid with `valid_to` later than `valid_from`."""
        if not valid_from and not valid_to:
            return {}
        errors = {}
        start, end = parse_date(valid_from), parse_date(valid_to)
        if start is None:
            errors["valid_from"] = "invalid_date"
        if end is None:
            errors["valid_to"] = "invalid_date"
        if start is not None and end is not None and end <= start:
            errors["valid_to"] = "end_not_after_start"
        return errors

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
        if row.week_pattern not in {p.value for p in WeekPattern}:
            errors["week_pattern"] = "invalid_choice"
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
            week_pattern=WeekPattern(row.week_pattern),
        )
