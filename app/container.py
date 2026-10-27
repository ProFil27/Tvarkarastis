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
from app.application.auth_service import AuthService
from app.infrastructure.persistence.user_repository import PostgresUserRepository
from app.infrastructure.security import WerkzeugPasswordHasher

# @imports:schedule_import

# @imports:work_shifts

from app.application.conflict_service import ConflictService
from app.application.week_view_service import WeekViewService
from app.infrastructure.ai.gemini_conflict_analyzer import GeminiConflictAnalyzer
from app.infrastructure.persistence.conflict_repository import PostgresConflictRepository
from app.infrastructure.persistence.notification_repository import PostgresNotificationRepository

@dataclass(frozen=True)
class Services:
    """Application services used by the web layer. Fields default to None so tests can wire only what they need."""

    auth: AuthService | None = None

# @fields:schedule_import

# @fields:work_shifts

    conflicts: ConflictService | None = None
    week_view: WeekViewService | None = None

def build_services(settings: Settings) -> Services:
    database = Database(settings)
    schedules = PostgresScheduleRepository(database)
    shifts = PostgresWorkShiftRepository(database)
    ai_log = PostgresAiRequestLog(database)
    gemini = GeminiClient(settings.gemini_api_key, settings.gemini_model)
    change_notifier = ChangeNotifier()

    auth = AuthService(PostgresUserRepository(database), WerkzeugPasswordHasher())

# @build:schedule_import

# @build:work_shifts

    conflict_repository = PostgresConflictRepository(database)
    notifications = PostgresNotificationRepository(database)
    conflicts = ConflictService(
        schedules, shifts, conflict_repository, notifications, GeminiConflictAnalyzer(gemini), ai_log
    )
    change_notifier.subscribe(conflicts.run_check)
    week_view = WeekViewService(schedules, shifts, conflict_repository, notifications)

    return Services(
        auth=auth,

# @kwargs:schedule_import

# @kwargs:work_shifts

        conflicts=conflicts,
        week_view=week_view,
    )
