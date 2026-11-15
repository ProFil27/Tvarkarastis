"""Timetable import: upload, AI recognition, review and confirmation (F-03..F-08)."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from app.application.errors import (
    RecognitionFailed,
    ReplaceConfirmationRequired,
    RowsValidationFailed,
    ValidationFailed,
)
from app.application.event_rows import ReviewRow, row_to_event, validate_row
from app.application.ports import (
    AiRequestLog,
    PdfDocumentRepository,
    ScheduleRecognizer,
    ScheduleRepository,
)
from app.application.validation import ChangeListener, ignore_changes, parse_date
from app.domain.clock import local_today
from app.domain.entities import AiRequestType, PdfStatus
from app.domain.rules import MAX_PDF_SIZE_BYTES, SEMESTER_LENGTH_DAYS


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
        today: Callable[[], date] = local_today,
    ):
        self._pdf_documents = pdf_documents
        self._schedules = schedules
        self._recognizer = recognizer
        self._ai_log = ai_log
        self._on_schedule_saved = on_schedule_saved
        self._today = today

    def upload_and_recognize(
        self, user_id: int, filename: str, content: bytes, consent_given: bool, replace_existing: bool = False
    ) -> RecognizedUpload:
        """Validate the file, run AI recognition and return rows for review.

        `replace_existing` is remembered with the PDF; the current schedule is not touched here (F-22).
        Raises ValidationFailed (field "file") or RecognitionFailed.
        """
        self._validate_upload(filename, content, consent_given)

        pdf_document = self._pdf_documents.add(user_id, filename, replace_existing)
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
        return [validate_row(row) for row in rows]

    def confirm(
        self,
        user_id: int,
        pdf_document_id: int,
        rows: list[ReviewRow],
        valid_from: str = "",
        valid_to: str = "",
        replace_confirmed: bool = False,
    ) -> int:
        """Persist the schedule only after the user confirmed it (F-08, N-24).

        `valid_from` / `valid_to` ("YYYY-MM-DD") are the schedule's validity period; when both are empty
        the schedule is valid from today for one semester.

        If the PDF was uploaded with "replace the existing schedule", the old schedule is removed together with
        saving the new one, but only once the user confirmed it (`replace_confirmed`); before that
        ReplaceConfirmationRequired(count) is raised and nothing changes (F-23).
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

        replacing = self._is_replacing(user_id, pdf_document_id)
        if replacing and not replace_confirmed:
            raise ReplaceConfirmationRequired(replacing)
        save = self._schedules.replace_all if replacing else self._schedules.add
        schedule_id = save(
            user_id=user_id,
            pdf_document_id=pdf_document_id,
            valid_from=period[0],
            valid_to=period[1],
            events=[row_to_event(row) for row in rows],
        )
        self._pdf_documents.set_status(pdf_document_id, PdfStatus.CONFIRMED)
        self._on_schedule_saved(user_id)
        return schedule_id

    def _is_replacing(self, user_id: int, pdf_document_id: int) -> int:
        """Number of existing events that would be removed; 0 if the PDF does not replace anything."""
        document = self._pdf_documents.get(pdf_document_id)
        if document is None or document.user_id != user_id or not document.replace_existing:
            return 0
        return self._schedules.count_events(user_id)

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
