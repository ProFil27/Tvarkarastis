"""Composition root: the only place that knows which concrete adapters are used.

Wires infrastructure implementations (Postgres, Gemini, hashing) into the
application services. Replacing the AI provider or the database means changing
this file and the adapters, not the services (N-19).
"""

from dataclasses import dataclass

from app.application.change_notifier import ChangeNotifier
from app.infrastructure.ai.gemini_client import GeminiClient
from app.infrastructure.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.persistence.ai_request_log import PostgresAiRequestLog
from app.infrastructure.persistence.schedule_repository import PostgresScheduleRepository
from app.infrastructure.persistence.work_shift_repository import PostgresWorkShiftRepository
# @imports:auth

from app.application.schedule_import_service import ScheduleImportService
from app.infrastructure.ai.gemini_schedule_recognizer import GeminiScheduleRecognizer
from app.infrastructure.persistence.pdf_document_repository import PostgresPdfDocumentRepository

# @imports:work_shifts

# @imports:conflicts

@dataclass(frozen=True)
class Services:
    """Application services used by the web layer. Fields default to None so tests can wire only what they need."""

# @fields:auth

    schedule_import: ScheduleImportService | None = None

# @fields:work_shifts

# @fields:conflicts

def build_services(settings: Settings) -> Services:
    database = Database(settings)
    schedules = PostgresScheduleRepository(database)
    shifts = PostgresWorkShiftRepository(database)
    ai_log = PostgresAiRequestLog(database)
    gemini = GeminiClient(settings.gemini_api_key, settings.gemini_model)
    change_notifier = ChangeNotifier()

# @build:auth

    schedule_import = ScheduleImportService(
        PostgresPdfDocumentRepository(database), schedules, GeminiScheduleRecognizer(gemini), ai_log, change_notifier
    )

# @build:work_shifts

# @build:conflicts

    return Services(
# @kwargs:auth

        schedule_import=schedule_import,

# @kwargs:work_shifts

# @kwargs:conflicts
    )
