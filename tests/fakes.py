"""In-memory implementations of the application ports, for tests."""

from dataclasses import replace
from datetime import date, datetime, time

from app.application.errors import AnalysisFailed, RecognitionFailed
from app.application.ports import AnalysisResult, RecognitionResult
from app.domain.entities import (
    Conflict,
    DetectedConflict,
    Notification,
    NotificationType,
    PdfDocument,
    PdfStatus,
    ReminderSetting,
    StudyEvent,
    StudyEventType,
    User,
    WeekPattern,
    WorkShift,
)
from app.domain.weekday import Weekday


class FakeHasher:
    def hash(self, password):
        return f"hashed:{password}"

    def verify(self, password, password_hash):
        return password_hash == f"hashed:{password}"


class FakeUserRepository:
    def __init__(self):
        self.users: dict[str, User] = {}

    def add(self, name, email, password_hash, ai_consent):
        user = User(len(self.users) + 1, name, email, password_hash, ai_consent)
        self.users[email] = user
        return user

    def get_by_email(self, email):
        return self.users.get(email)


class FakePdfDocumentRepository:
    def __init__(self):
        self.documents: dict[int, PdfDocument] = {}

    def add(self, user_id, filename, replace_existing=False):
        document = PdfDocument(len(self.documents) + 1, user_id, filename, PdfStatus.UPLOADED, replace_existing)
        self.documents[document.id] = document
        return document

    def get(self, pdf_document_id):
        return self.documents.get(pdf_document_id)

    def set_status(self, pdf_document_id, status):
        self.documents[pdf_document_id] = replace(self.documents[pdf_document_id], status=status)


class FakeScheduleRepository:
    def __init__(self):
        self.events: dict[int, list[StudyEvent]] = {}
        self.saved_schedules: list[dict] = []
        self.replaced: list[int] = []  # users whose old schedule was removed by replace_all
        self.last_upload: dict[int, date] = {}  # date of the user's last saved schedule (tests set it)
        self._next_id = 0

    def add(self, user_id, pdf_document_id, valid_from, valid_to, events):
        numbered = [replace(e, id=self._new_id()) for e in events]  # validity stays as given on the event
        self.events.setdefault(user_id, []).extend(numbered)
        self.saved_schedules.append({"user_id": user_id, "valid_from": valid_from, "valid_to": valid_to})
        return len(self.saved_schedules)

    def list_study_events(self, user_id, week_start=None, week_end=None):
        return list(self.events.get(user_id, []))

    def count_events(self, user_id):
        return len(self.events.get(user_id, []))

    def replace_all(self, user_id, pdf_document_id, valid_from, valid_to, events):
        self.events[user_id] = []
        self.replaced.append(user_id)
        return self.add(user_id, pdf_document_id, valid_from, valid_to, events)

    def last_schedule_date(self, user_id):
        return self.last_upload.get(user_id)

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    def get_event(self, user_id, event_id):
        return next((e for e in self.events.get(user_id, []) if e.id == event_id), None)

    def add_event(self, user_id, event, default_from, default_to):
        if not self.events.get(user_id):
            self.saved_schedules.append({"user_id": user_id, "valid_from": default_from, "valid_to": default_to})
        stored = replace(event, id=self._new_id(), valid_from=default_from, valid_to=default_to, updated_at=datetime.now())
        self.events.setdefault(user_id, []).append(stored)
        return stored

    def update_event(self, user_id, event_id, event):
        old = self.get_event(user_id, event_id)
        if old is None:
            return None
        new = replace(event, id=event_id, valid_from=old.valid_from, valid_to=old.valid_to, updated_at=datetime.now())
        self.events[user_id] = [new if e.id == event_id else e for e in self.events[user_id]]
        return new

    def remove_event(self, user_id, event_id):
        before = self.events.get(user_id, [])
        self.events[user_id] = [e for e in before if e.id != event_id]
        return len(self.events[user_id]) != len(before)


class FakeReminderSettingRepository:
    def __init__(self):
        self.settings: dict[int, ReminderSetting] = {}

    def get(self, user_id):
        return self.settings.get(user_id, ReminderSetting(user_id))

    def set_enabled(self, user_id, enabled):
        self.settings[user_id] = replace(self.get(user_id), enabled=enabled)

    def set_closed_period(self, user_id, period_start, reminder_type):
        self.settings[user_id] = replace(self.get(user_id), closed_period_start=period_start)


class FakeWorkShiftRepository:
    def __init__(self):
        self.shifts: dict[int, list[WorkShift]] = {}
        self._next_id = 1

    def add(self, user_id, workplace_name, work_date, start_time, end_time):
        shift = WorkShift(self._next_id, workplace_name, work_date, start_time, end_time, datetime.now())
        self._next_id += 1
        self.shifts.setdefault(user_id, []).append(shift)
        return shift

    def list_for_user(self, user_id):
        return list(self.shifts.get(user_id, []))

    def get(self, user_id, shift_id):
        return next((s for s in self.shifts.get(user_id, []) if s.id == shift_id), None)

    def update(self, user_id, shift_id, workplace_name, work_date, start_time, end_time):
        if self.get(user_id, shift_id) is None:
            return None
        new = WorkShift(shift_id, workplace_name, work_date, start_time, end_time, datetime.now())
        self.shifts[user_id] = [new if s.id == shift_id else s for s in self.shifts[user_id]]
        return new

    def remove(self, user_id, shift_id):
        before = self.shifts.get(user_id, [])
        after = [s for s in before if s.id != shift_id]
        self.shifts[user_id] = after
        return len(after) != len(before)


class FakeConflictRepository:
    def __init__(self):
        self.active: dict[int, list[Conflict]] = {}
        self.resolved: list[Conflict] = []  # conflicts that disappeared (status ISSPRESTAS)
        self._next_id = 1

    def list_active(self, user_id):
        return list(self.active.get(user_id, []))

    def replace_active(self, user_id, detected):
        existing = {(c.study_event_id, c.work_shift_id): c for c in self.active.get(user_id, [])}
        detected_keys = {(d.study_event_id, d.work_shift_id) for d in detected}
        self.resolved.extend(c for key, c in existing.items() if key not in detected_keys)
        result, created = [], []
        for item in detected:
            key = (item.study_event_id, item.work_shift_id)
            if key in existing:
                result.append(replace(existing[key], overlap_minutes=item.overlap_minutes))
            else:
                conflict = Conflict(self._next_id, *key, item.overlap_minutes)
                self._next_id += 1
                result.append(conflict)
                created.append(conflict)
        self.active[user_id] = result
        return created


class FakeNotificationRepository:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, user_id, conflict_id, message, notification_type=NotificationType.CONFLICT):
        self.items.append(
            {"id": len(self.items) + 1, "user_id": user_id, "message": message, "read": False, "type": notification_type}
        )

    def list_unread(self, user_id):
        return [
            Notification(i["id"], i["message"], i["type"])
            for i in self.items
            if i["user_id"] == user_id and not i["read"]
        ]

    def mark_read(self, user_id, notification_id):
        for item in self.items:
            if item["id"] == notification_id and item["user_id"] == user_id:
                item["read"] = True
                return True
        return False


class FakeAiRequestLog:
    def __init__(self):
        self.requests: list[dict] = []

    def start(self, user_id, request_type, pdf_document_id=None):
        self.requests.append({"type": request_type, "attempts": 0, "error": None})
        return len(self.requests) - 1

    def finish(self, ai_request_id, attempts, error):
        self.requests[ai_request_id].update(attempts=attempts, error=error)


MONDAY = date(2026, 10, 26)  # a Monday; sample shifts fall on it
TUESDAY = date(2026, 10, 27)


def sample_event(
    event_id=None, weekday=Weekday.MONDAY, start=time(9, 0), end=time(10, 30), subject="Programavimas",
    week_pattern=WeekPattern.EVERY_WEEK,
):
    return StudyEvent(
        event_id, subject, StudyEventType.LECTURE, weekday, start, end, "A1", True, week_pattern=week_pattern
    )


class FakeRecognizer:
    def __init__(self, events=None, fail=False):
        self.events = events if events is not None else [sample_event()]
        self.fail = fail

    def recognize(self, pdf_content):
        if self.fail:
            raise RecognitionFailed("boom", 3)
        return RecognitionResult(self.events, 1)


class FakeAnalyzer:
    """Returns a fixed list of detected conflicts (can include wrong ones, to test verification)."""

    def __init__(self, detected=None, fail=False):
        self.detected = detected or []
        self.fail = fail

    def analyze(self, events, shifts):
        if self.fail:
            raise AnalysisFailed("Failed", 3)
        return AnalysisResult(list(self.detected), 1)
