"""Composition root: the only place that knows which concrete adapters are used.

Wires infrastructure implementations (Postgres, the selected AI provider, hashing) into the
application services. Replacing the AI provider or the database means changing
this file and the adapters, not the services (N-19).
"""

from dataclasses import dataclass

from app.application.auth_service import AuthService
from app.application.calendar_sync_service import CalendarSyncService
from app.application.change_notifier import ChangeNotifier
from app.application.conflict_service import ConflictService
from app.application.reminder_service import ReminderService
from app.application.schedule_import_service import ScheduleImportService
from app.application.study_event_service import StudyEventService
from app.application.week_view_service import WeekViewService
from app.application.work_shift_service import WorkShiftService
from app.infrastructure.ai.claude_client import ClaudeClient
from app.infrastructure.ai.gemini_client import GeminiClient
from app.infrastructure.ai.gemini_conflict_analyzer import ConflictAnalyzer
from app.infrastructure.ai.gemini_schedule_recognizer import ScheduleRecognizer
from app.infrastructure.calendar.google_calendar_client import GoogleCalendarClient
from app.infrastructure.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.persistence.ai_request_log import PostgresAiRequestLog
from app.infrastructure.persistence.calendar_account_repository import PostgresCalendarAccountRepository
from app.infrastructure.persistence.conflict_repository import PostgresConflictRepository
from app.infrastructure.persistence.notification_repository import PostgresNotificationRepository
from app.infrastructure.persistence.pdf_document_repository import PostgresPdfDocumentRepository
from app.infrastructure.persistence.reminder_repository import PostgresReminderSettingRepository
from app.infrastructure.persistence.schedule_repository import PostgresScheduleRepository
from app.infrastructure.persistence.user_repository import PostgresUserRepository
from app.infrastructure.persistence.work_shift_repository import PostgresWorkShiftRepository
from app.infrastructure.security import FernetTokenCipher, WerkzeugPasswordHasher


@dataclass(frozen=True)
class Services:
    """Application services used by the web layer. Fields default to None so tests can wire only what they need."""

    auth: AuthService | None = None
    schedule_import: ScheduleImportService | None = None
    study_events: StudyEventService | None = None
    work_shifts: WorkShiftService | None = None
    conflicts: ConflictService | None = None
    week_view: WeekViewService | None = None
    reminders: ReminderService | None = None
    calendar: CalendarSyncService | None = None


def build_services(settings: Settings) -> Services:
    database = Database(settings)
    schedules = PostgresScheduleRepository(database)
    shifts = PostgresWorkShiftRepository(database)
    ai_log = PostgresAiRequestLog(database)
    if settings.ai_provider == "claude":
        ai_client = ClaudeClient(settings.claude_api_key, settings.claude_model)
    else:
        ai_client = GeminiClient(settings.gemini_api_key, settings.gemini_model)
    change_notifier = ChangeNotifier()

    auth = AuthService(PostgresUserRepository(database), WerkzeugPasswordHasher())

    schedule_import = ScheduleImportService(
        PostgresPdfDocumentRepository(database), schedules, ScheduleRecognizer(ai_client), ai_log, change_notifier
    )

    study_events = StudyEventService(schedules, change_notifier)
    work_shifts = WorkShiftService(shifts, change_notifier)

    conflict_repository = PostgresConflictRepository(database)
    notifications = PostgresNotificationRepository(database)
    conflicts = ConflictService(
        schedules, shifts, conflict_repository, notifications, ConflictAnalyzer(ai_client), ai_log
    )
    change_notifier.subscribe(conflicts.run_check)
    week_view = WeekViewService(schedules, shifts, conflict_repository, notifications)

    reminders = ReminderService(PostgresReminderSettingRepository(database), schedules, settings.semester_start_dates)

    calendar = CalendarSyncService(
        GoogleCalendarClient(settings.google_client_id, settings.google_client_secret, settings.google_redirect_uri),
        PostgresCalendarAccountRepository(database),
        FernetTokenCipher(settings.token_encryption_key),
    )

    return Services(
        auth=auth,
        schedule_import=schedule_import,
        study_events=study_events,
        work_shifts=work_shifts,
        conflicts=conflicts,
        week_view=week_view,
        reminders=reminders,
        calendar=calendar,
    )
