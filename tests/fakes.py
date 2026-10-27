"""In-memory implementations of the application ports, for tests."""

from dataclasses import replace
from datetime import date, time

from app.application.errors import AnalysisFailed, RecognitionFailed
from app.application.ports import AnalysisResult, RecognitionResult
from app.domain.entities import (
    Conflict,
    DetectedConflict,
    Notification,
    PdfDocument,
    PdfStatus,
    StudyEvent,
    StudyEventType,
    User,
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

    def add(self, user_id, filename):
        document = PdfDocument(len(self.documents) + 1, user_id, filename, PdfStatus.UPLOADED)
        self.documents[document.id] = document
        return document

    def set_status(self, pdf_document_id, status):
        self.documents[pdf_document_id] = replace(self.documents[pdf_document_id], status=status)


class FakeScheduleRepository:
    def __init__(self):
        self.events: dict[int, list[StudyEvent]] = {}
        self.saved_schedules: list[dict] = []

    def add(self, user_id, pdf_document_id, valid_from, valid_to, events):
        numbered = [replace(e, id=len(self.events.get(user_id, [])) + i + 1) for i, e in enumerate(events)]
        self.events.setdefault(user_id, []).extend(numbered)
        self.saved_schedules.append({"user_id": user_id, "valid_from": valid_from, "valid_to": valid_to})
        return len(self.saved_schedules)

    def list_study_events(self, user_id, week_start=None, week_end=None):
        return list(self.events.get(user_id, []))


class FakeWorkShiftRepository:
    def __init__(self):
        self.shifts: dict[int, list[WorkShift]] = {}
        self._next_id = 1

    def add(self, user_id, workplace_name, weekday, start_time, end_time):
        shift = WorkShift(self._next_id, workplace_name, weekday, start_time, end_time)
        self._next_id += 1
        self.shifts.setdefault(user_id, []).append(shift)
        return shift

    def list_for_user(self, user_id):
        return list(self.shifts.get(user_id, []))

    def remove(self, user_id, shift_id):
        before = self.shifts.get(user_id, [])
        after = [s for s in before if s.id != shift_id]
        self.shifts[user_id] = after
        return len(after) != len(before)


class FakeConflictRepository:
    def __init__(self):
        self.active: dict[int, list[Conflict]] = {}
        self._next_id = 1

    def list_active(self, user_id):
        return list(self.active.get(user_id, []))

    def replace_active(self, user_id, detected):
        existing = {(c.study_event_id, c.work_shift_id): c for c in self.active.get(user_id, [])}
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

    def add(self, user_id, conflict_id, message):
        self.items.append({"id": len(self.items) + 1, "user_id": user_id, "message": message, "read": False})

    def list_unread(self, user_id):
        return [Notification(i["id"], i["message"]) for i in self.items if i["user_id"] == user_id and not i["read"]]

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


def sample_event(event_id=None, weekday=Weekday.MONDAY, start=time(9, 0), end=time(10, 30), subject="Programavimas"):
    return StudyEvent(event_id, subject, StudyEventType.LECTURE, weekday, start, end, "A1", True)


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
            raise AnalysisFailed("boom", 3)
        return AnalysisResult(list(self.detected), 1)
