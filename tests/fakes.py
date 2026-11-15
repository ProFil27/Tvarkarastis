"""In-memory implementations of the application ports, for tests."""

from dataclasses import replace
from datetime import date, datetime, time

from app.application.errors import AnalysisFailed, CalendarError, RecognitionFailed
from app.application.ports import AnalysisResult, AuthorizationRequest, RecognitionResult
from app.domain.entities import (
    CalendarAccount,
    CalendarAccountStatus,
    CalendarEventLink,
    CalendarTokens,
    Conflict,
    Notification,
    NotificationType,
    PdfDocument,
    PdfStatus,
    ReminderSetting,
    StudyEvent,
    StudyEventType,
    SyncOperation,
    SyncOperationType,
    SyncStatus,
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
        stored = replace(
            event, id=self._new_id(), valid_from=default_from, valid_to=default_to, updated_at=datetime.now()
        )
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
            {
                "id": len(self.items) + 1, "user_id": user_id, "message": message, "read": False,
                "type": notification_type,
            }
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


class FakeTokenCipher:
    """Reversible stand-in for the Fernet cipher; ciphertext is recognisable in assertions."""

    def __init__(self, available=True):
        self._available = available

    @property
    def available(self):
        return self._available

    def encrypt(self, plain_text):
        if not self._available:
            raise CalendarError(CalendarError.NOT_CONFIGURED)
        return "enc:" + plain_text

    def decrypt(self, cipher_text):
        if not cipher_text.startswith("enc:"):
            raise CalendarError(CalendarError.AUTH_EXPIRED)
        return cipher_text[len("enc:"):]


class FakeCalendarAccountRepository:
    def __init__(self):
        self.accounts: dict[int, CalendarAccount] = {}

    def get(self, user_id):
        return self.accounts.get(user_id)

    def save_connected(self, user_id, google_email, access_token_enc, refresh_token_enc, token_expires_at,
                       consent_given_at, connected_at):
        account = CalendarAccount(user_id, CalendarAccountStatus.CONNECTED, google_email, access_token_enc,
                                  refresh_token_enc, token_expires_at, consent_given_at, connected_at)
        self.accounts[user_id] = account
        return account

    def update_tokens(self, user_id, access_token_enc, refresh_token_enc, token_expires_at):
        old = self.accounts[user_id]
        self.accounts[user_id] = replace(
            old, access_token_enc=access_token_enc, token_expires_at=token_expires_at,
            refresh_token_enc=refresh_token_enc or old.refresh_token_enc,
        )

    def set_status(self, user_id, status):
        self.accounts[user_id] = replace(self.accounts[user_id], status=status)


class FakeCalendarProvider:
    """Records what the sync does; `errors` maps a method name to the CalendarError it should raise."""

    def __init__(self, configured=True, errors=None):
        self.configured = configured
        self.errors = errors or {}
        self.calls: list[tuple] = []
        self.events: dict[str, dict] = {}  # the events that exist in the user's Google calendar
        self._next_event = 0
        self.tokens = CalendarTokens("access-1", "refresh-1", datetime(2099, 1, 1), "student@gmail.com")

    def is_configured(self):
        return self.configured

    def _maybe_fail(self, method):
        error = self.errors.get(method)
        if error is not None:
            raise error

    def authorization_url(self, state):
        self.calls.append(("authorization_url", state))
        return AuthorizationRequest(f"https://accounts.example.com/auth?state={state}", "verifier-1")

    def exchange_code(self, code, code_verifier):
        self.calls.append(("exchange_code", code, code_verifier))
        self._maybe_fail("exchange_code")
        return self.tokens

    def refresh(self, tokens):
        self.calls.append(("refresh",))
        self._maybe_fail("refresh")
        return replace(tokens, access_token="access-2", expires_at=datetime(2099, 1, 2))

    # -- an in-memory Google calendar: id -> event body
    def create_event(self, tokens, body):
        self.calls.append(("create_event", tokens.access_token))
        self._maybe_fail("create_event")
        self._next_event += 1
        google_id = f"g{self._next_event}"
        self.events[google_id] = body
        return google_id

    def update_event(self, tokens, google_event_id, body):
        self.calls.append(("update_event", google_event_id))
        self._maybe_fail("update_event")
        if google_event_id not in self.events:
            raise CalendarError(CalendarError.NOT_FOUND)
        self.events[google_event_id] = body

    def delete_event(self, tokens, google_event_id):
        self.calls.append(("delete_event", google_event_id))
        self._maybe_fail("delete_event")
        self.events.pop(google_event_id, None)

    def calls_named(self, name):
        return [call for call in self.calls if call[0] == name]


class FakeCalendarEventRepository:
    """Links between local records and Google events; `unlink_study_event` mimics ON DELETE SET NULL."""

    def __init__(self):
        self.links: dict[int, CalendarEventLink] = {}
        self._next_id = 0

    def list_links(self, user_id):
        return [link for link in self.links.values() if link.user_id == user_id]

    def add_link(self, user_id, study_event_id, work_shift_id, google_event_id, synced_at):
        self._next_id += 1
        link = CalendarEventLink(self._next_id, user_id, study_event_id, work_shift_id, google_event_id, synced_at)
        self.links[link.id] = link
        return link

    def touch_link(self, link_id, synced_at):
        self.links[link_id] = replace(self.links[link_id], synced_at=synced_at)

    def replace_google_event(self, link_id, google_event_id, synced_at):
        self.links[link_id] = replace(self.links[link_id], google_event_id=google_event_id, synced_at=synced_at)

    def remove_link(self, link_id):
        del self.links[link_id]

    def unlink_study_event(self, event_id):
        for link in list(self.links.values()):
            if link.study_event_id == event_id:
                self.links[link.id] = replace(link, study_event_id=None)

    def unlink_work_shift(self, shift_id):
        for link in list(self.links.values()):
            if link.work_shift_id == shift_id:
                self.links[link.id] = replace(link, work_shift_id=None)


class FakeSyncOperationRepository:
    def __init__(self):
        self.operations: list[SyncOperation] = []

    def start(self, user_id, operation_type, started_at):
        self.operations.append(SyncOperation(len(self.operations) + 1, user_id, operation_type,
                                             SyncStatus.IN_PROGRESS, started_at))
        return len(self.operations)

    def finish(self, operation_id, status, finished_at, created, updated, deleted, error_code=None, error_message=None):
        old = self.operations[operation_id - 1]
        self.operations[operation_id - 1] = replace(
            old, status=status, finished_at=finished_at, created_count=created, updated_count=updated,
            deleted_count=deleted, error_code=error_code, error_message=error_message,
        )

    def _finished(self, user_id, only_success=False):
        found = [o for o in self.operations if o.user_id == user_id and o.status != SyncStatus.IN_PROGRESS
                 and (o.status == SyncStatus.SUCCESS or not only_success)]
        return found[-1] if found else None

    def last(self, user_id):
        return self._finished(user_id)

    def last_success(self, user_id):
        return self._finished(user_id, only_success=True)

    def has_export(self, user_id):
        return any(o.user_id == user_id and o.operation_type == SyncOperationType.EXPORT
                   and o.status == SyncStatus.SUCCESS for o in self.operations)
