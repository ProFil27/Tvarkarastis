"""KSK: connecting the user's Google Calendar account, exporting the schedule and reporting the state
(F-24..F-31).

The service knows the calendar only through the CalendarProvider port (N-41, N-42). OAuth tokens are encrypted
before they are stored and are never logged (N-43). Only events whose Google id is stored in a link are ever
changed or deleted (N-45); a record that already has a link is updated, never created again (F-29, N-32).
"""

import hmac
import logging
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.application.background import CoalescingRunner, start_thread
from app.application.calendar_events import shift_series_body, study_event_body, work_shift_body
from app.application.calendar_texts import calendar_error_text
from app.application.errors import CalendarError
from app.application.ports import (
    CalendarAccountRepository,
    CalendarEventRepository,
    CalendarProvider,
    NotificationRepository,
    ScheduleRepository,
    ShiftSeriesRepository,
    SyncOperationRepository,
    TokenCipher,
    WorkShiftRepository,
)
from app.domain.clock import local_now
from app.domain.entities import (
    CalendarAccount,
    CalendarAccountStatus,
    CalendarEventLink,
    CalendarTokens,
    NotificationType,
    SyncOperation,
    SyncOperationType,
    SyncStatus,
)

log = logging.getLogger(__name__)

STATE_BYTES = 32  # 256 bits, more than the 128 required by N-44
TOKEN_EXPIRY_MARGIN = timedelta(seconds=60)


@dataclass(frozen=True)
class ConnectRequest:
    """Redirect the user to `url`; keep `state` and `code_verifier` in their session until the callback."""

    url: str
    state: str
    code_verifier: str


@dataclass(frozen=True)
class SyncResult:
    created: int = 0
    updated: int = 0
    deleted: int = 0


@dataclass(frozen=True)
class CalendarStatusReport:
    """What the calendar window shows (F-30)."""

    status: CalendarAccountStatus
    google_email: str | None = None
    connected_at: datetime | None = None
    exported: bool = False  # a successful export has been made
    last_success_at: datetime | None = None
    last_operation: SyncOperation | None = None  # the most recent finished run, successful or not
    last_error: SyncOperation | None = None  # set only when that run failed
    syncing: bool = False  # an update after a change is running in the background


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class _Run:
    """The OAuth tokens of one synchronisation run; they are refreshed at most when they expire or are rejected."""

    def __init__(self, user_id: int, tokens: CalendarTokens):
        self.user_id = user_id
        self.tokens = tokens


class CalendarSyncService:
    def __init__(
        self,
        provider: CalendarProvider,
        accounts: CalendarAccountRepository,
        cipher: TokenCipher,
        links: CalendarEventRepository,
        operations: SyncOperationRepository,
        schedules: ScheduleRepository,
        shifts: WorkShiftRepository,
        series: ShiftSeriesRepository,
        notifications: NotificationRepository,
        now: Callable[[], datetime] = local_now,
        utc_now: Callable[[], datetime] = _utc_now,
        background: bool = False,
        workers: int = 1,
    ):
        self._provider = provider
        self._accounts = accounts
        self._cipher = cipher
        self._links = links
        self._operations = operations
        self._schedules = schedules
        self._shifts = shifts
        self._series = series
        self._notifications = notifications
        self._now = now  # local time, shown to the user and sent to the calendar (N-29)
        self._utc_now = utc_now  # token expiry is kept in UTC
        # Updates after a change run in the background (`background=True`) so saving stays instant;
        # tests run them inline.
        self._runner = CoalescingRunner(self._update_after_change, start_thread if background else lambda work: work())
        self._workers = max(1, workers)  # calendar requests of one run that are sent side by side (N-35)
        self._refresh_lock = threading.Lock()
        self._locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ------------------------------------------------------------------ connecting (F-24, F-25)

    def is_available(self) -> bool:
        """False when the Google settings or the token encryption key are missing."""
        return self._provider.is_configured() and self._cipher.available

    def begin_connect(self, user_id: int, consent_given: bool) -> ConnectRequest:
        """Check the consent and build Google's approval page address. Raises CalendarError."""
        if not self.is_available():
            raise CalendarError(CalendarError.NOT_CONFIGURED)
        if not consent_given:
            raise CalendarError(CalendarError.CONSENT_REQUIRED)
        state = secrets.token_urlsafe(STATE_BYTES)
        request = self._provider.authorization_url(state)
        return ConnectRequest(request.url, state, request.code_verifier)

    def complete_connect(
        self,
        user_id: int,
        code: str | None,
        state: str | None,
        expected_state: str | None,
        code_verifier: str | None,
        error: str | None = None,
    ) -> CalendarAccount:
        """Finish the sign-in after Google sent the user back. Raises CalendarError.

        On any failure the account is left as it was and no token is stored (F-25).
        """
        if error:
            if error == "access_denied":
                raise CalendarError(CalendarError.ACCESS_DENIED)
            raise CalendarError(CalendarError.INVALID_CODE, error)
        if not expected_state or not state or not hmac.compare_digest(state, expected_state):
            raise CalendarError(CalendarError.INVALID_STATE)
        if not code or not code_verifier:
            raise CalendarError(CalendarError.INVALID_CODE)
        if not self.is_available():
            raise CalendarError(CalendarError.NOT_CONFIGURED)

        tokens = self._provider.exchange_code(code, code_verifier)
        now = self._now()
        return self._accounts.save_connected(
            user_id,
            tokens.email,
            self._cipher.encrypt(tokens.access_token),
            self._cipher.encrypt(tokens.refresh_token) if tokens.refresh_token else None,
            tokens.expires_at,
            consent_given_at=now,
            connected_at=now,
        )

    # ------------------------------------------------------------------ export / update (F-26..F-29)

    def export(self, user_id: int) -> SyncResult:
        """Put the user's study events and work shifts into their Google Calendar (F-26, F-27).

        Raises CalendarError when the account is not connected or the calendar service fails; the run is
        recorded either way. Running it again never creates duplicates: records that already have a Google
        event are updated instead (F-29).
        """
        return self._reconcile(user_id, SyncOperationType.EXPORT)

    def sync(self, user_id: int) -> SyncResult:
        """Bring Google Calendar in line with the user's records: create new, update changed, delete removed
        (F-28). Needs a connected account and an earlier export. Raises CalendarError.
        """
        self._connected_account(user_id)
        if not self._operations.has_export(user_id):
            raise CalendarError(CalendarError.NOT_EXPORTED)
        return self._reconcile(user_id, SyncOperationType.UPDATE)

    def on_data_changed(self, user_id: int) -> None:
        """ChangeNotifier listener: update the calendar after a lecture, shift or schedule changed (F-28).

        Does nothing if the calendar is not connected or nothing was exported yet. It never raises (N-33,
        N-34): a failure is recorded, the user gets a system notification, and the saved change stays.
        """
        account = self._accounts.get(user_id)
        if account is None or account.status != CalendarAccountStatus.CONNECTED:
            return
        if not self._operations.has_export(user_id):
            return
        self._runner.request(user_id)

    def _update_after_change(self, user_id: int) -> None:
        try:
            self._reconcile(user_id, SyncOperationType.UPDATE)
        except CalendarError:
            pass  # recorded and notified by the run itself
        except Exception:  # noqa: BLE001 - the saved change must survive any calendar problem
            log.exception("Calendar update after a change failed")

    def _lock_for(self, user_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(user_id, threading.Lock())

    def _notify_failure(self, user_id: int, code: str) -> None:
        """One system notification per distinct problem until the user dismisses it (F-31)."""
        message = "Kalendoriaus sinchronizavimas nepavyko. " + calendar_error_text(code)
        if any(n.message == message for n in self._notifications.list_unread(user_id)):
            return
        self._notifications.add(user_id, None, message, NotificationType.SYNC_ERROR)

    def _reconcile(self, user_id: int, operation_type: SyncOperationType) -> SyncResult:
        with self._lock_for(user_id):  # a manual run and the background update never overlap (no duplicates)
            return self._reconcile_locked(user_id, operation_type)

    def _reconcile_locked(self, user_id: int, operation_type: SyncOperationType) -> SyncResult:
        account = self._connected_account(user_id)
        operation_id = self._operations.start(user_id, operation_type, self._now())
        created = updated = deleted = 0
        try:
            run = self._open_run(account)
            events = self._schedules.list_study_events(user_id)
            shifts = self._shifts.list_for_user(user_id)
            links = self._links.list_links(user_id)
            for_event = {link.study_event_id: link for link in links if link.study_event_id is not None}
            for_shift = {link.work_shift_id: link for link in links if link.work_shift_id is not None}
            for_series = {link.shift_series_id: link for link in links if link.shift_series_id is not None}
            today = self._now().date()

            # (Google event, its link, change time, study event id, shift id, series id)
            wanted = [
                (study_event_body(event, today), for_event.get(event.id), event.updated_at, event.id, None, None)
                for event in events
            ]
            # shifts that follow a weekly series are exported once, as the series; the rest one by one
            wanted += [
                (work_shift_body(shift), for_shift.get(shift.id), shift.updated_at, None, shift.id, None)
                for shift in shifts
                if not shift.follows_series
            ]
            for series in self._series.list_for_user(user_id):
                members = [shift for shift in shifts if shift.series_id == series.id and shift.follows_series]
                body = None
                if members:
                    body = shift_series_body(
                        members[0].workplace_name, series.start_time, series.end_time, [m.work_date for m in members]
                    )
                wanted.append((body, for_series.get(series.id), series.updated_at, None, None, series.id))

            creates, updates, deletes = [], [], []
            for body, link, changed_at, event_id, shift_id, series_id in wanted:
                if body is None:
                    if link is not None:  # nothing left to show (e.g. every shift of a series changed or removed)
                        deletes.append(link)
                    continue  # a study event that never takes place inside its schedule's validity period
                if link is None:
                    creates.append((body, event_id, shift_id, series_id))
                elif changed_at is not None and changed_at > link.synced_at:
                    updates.append((link, body))
            deletes += [link for link in links if link.is_orphan]  # the local record is gone: delete our event only

            # The requests of each step are independent, so they are sent side by side. Their results are recorded
            # here one by one, so every event that was created gets its link even if a later request fails (N-32).
            outcomes = self._send([lambda t, b=body: self._provider.create_event(t, b) for body, *_ in creates], run)
            error = None
            for (body, event_id, shift_id, series_id), (google_id, failure) in zip(creates, outcomes):
                if failure is not None:
                    error = error or failure
                    continue
                self._links.add_link(user_id, event_id, shift_id, google_id, self._now(), series_id)
                created += 1
            if error:
                raise error

            outcomes = self._send([self._update_task(link, body) for link, body in updates], run)
            for (link, body), (result, failure) in zip(updates, outcomes):
                if failure is not None:
                    error = error or failure
                elif result is None:
                    self._links.touch_link(link.id, self._now())
                    updated += 1
                else:  # the user deleted the event in Google: it was created again
                    self._links.replace_google_event(link.id, result, self._now())
                    created += 1
            if error:
                raise error

            outcomes = self._send([lambda t, g=link.google_event_id: self._provider.delete_event(t, g)
                                   for link in deletes], run)
            for link, (_, failure) in zip(deletes, outcomes):
                if failure is not None:
                    error = error or failure
                    continue
                self._links.remove_link(link.id)
                deleted += 1
            if error:
                raise error
        except CalendarError as exc:
            self._fail(account, operation_id, exc.code, str(exc), created, updated, deleted)
            raise
        except Exception as exc:  # noqa: BLE001 - never leave a run "in progress" or leak details to the user
            log.exception("Unexpected calendar synchronisation error")
            self._fail(account, operation_id, CalendarError.UNAVAILABLE, type(exc).__name__, created, updated, deleted)
            raise CalendarError(CalendarError.UNAVAILABLE) from exc

        self._operations.finish(operation_id, SyncStatus.SUCCESS, self._now(), created, updated, deleted)
        return SyncResult(created, updated, deleted)

    def _update_task(self, link: CalendarEventLink, body: dict) -> Callable[[CalendarTokens], str | None]:
        """Request that updates the linked Google event; if the user deleted it in Google it is created again and
        the id of the new event is returned (None when the update worked)."""

        def update(tokens: CalendarTokens) -> str | None:
            try:
                self._provider.update_event(tokens, link.google_event_id, body)
            except CalendarError as exc:
                if exc.code != CalendarError.NOT_FOUND:
                    raise
                return self._provider.create_event(tokens, body)
            return None

        return update

    def _send(
        self, requests: list[Callable[[CalendarTokens], object]], run: _Run
    ) -> list[tuple[object, Exception | None]]:
        """Send independent calendar requests and return (result, error) per request, in order.

        With several workers the requests run side by side; with one they run in turn and stop at the first error.
        """
        def one(request):
            try:
                return self._call(run, request), None
            except Exception as exc:  # noqa: BLE001 - reported to the caller, which records what succeeded first
                return None, exc

        if self._workers == 1 or len(requests) < 2:
            outcomes = []
            for request in requests:
                outcomes.append(one(request))
                if outcomes[-1][1] is not None:
                    break
            return outcomes
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            return list(pool.map(one, requests))

    def _fail(
        self,
        account: CalendarAccount,
        operation_id: int,
        code: str,
        detail: str,
        created: int,
        updated: int,
        deleted: int,
    ) -> None:
        if code == CalendarError.AUTH_EXPIRED:
            self._accounts.set_status(account.user_id, CalendarAccountStatus.RECONNECT_REQUIRED)
        self._operations.finish(operation_id, SyncStatus.ERROR, self._now(), created, updated, deleted, code, detail)
        self._notify_failure(account.user_id, code)

    # ------------------------------------------------------------------ tokens (N-31, N-33, N-43)

    def _connected_account(self, user_id: int) -> CalendarAccount:
        account = self._accounts.get(user_id)
        if account is None or account.status == CalendarAccountStatus.NOT_CONNECTED:
            raise CalendarError(CalendarError.NOT_CONNECTED)
        if account.status == CalendarAccountStatus.RECONNECT_REQUIRED:
            raise CalendarError(CalendarError.AUTH_EXPIRED)
        return account

    def _open_run(self, account: CalendarAccount) -> _Run:
        """Decrypt the stored tokens and make sure the access token is still valid."""
        if not account.access_token_enc:
            raise CalendarError(CalendarError.AUTH_EXPIRED)
        tokens = CalendarTokens(
            self._cipher.decrypt(account.access_token_enc),
            self._cipher.decrypt(account.refresh_token_enc) if account.refresh_token_enc else None,
            account.token_expires_at,
            account.google_email,
        )
        run = _Run(account.user_id, tokens)
        if tokens.expires_at is None or tokens.expires_at <= self._utc_now() + TOKEN_EXPIRY_MARGIN:
            self._refresh(run)
        return run

    def _refresh(self, run: _Run) -> None:
        with self._refresh_lock:
            self._refresh_locked(run)

    def _refresh_locked(self, run: _Run) -> None:
        refreshed = self._provider.refresh(run.tokens)
        self._accounts.update_tokens(
            run.user_id,
            self._cipher.encrypt(refreshed.access_token),
            self._cipher.encrypt(refreshed.refresh_token) if refreshed.refresh_token else None,
            refreshed.expires_at,
        )
        run.tokens = refreshed

    def _call(self, run: _Run, action: Callable[[CalendarTokens], object]):
        """Run one calendar request; if the access token is rejected, refresh it once and try again."""
        try:
            return action(run.tokens)
        except CalendarError as exc:
            if exc.code != CalendarError.AUTH_EXPIRED:
                raise
        self._refresh(run)  # raises AUTH_EXPIRED if the refresh token no longer works
        return action(run.tokens)

    # ------------------------------------------------------------------ state (F-30)

    def status(self, user_id: int) -> CalendarStatusReport:
        account = self._accounts.get(user_id)
        if account is None:
            return CalendarStatusReport(CalendarAccountStatus.NOT_CONNECTED)
        last = self._operations.last(user_id)
        last_success = self._operations.last_success(user_id)
        return CalendarStatusReport(
            status=account.status,
            google_email=account.google_email,
            connected_at=account.connected_at,
            exported=self._operations.has_export(user_id),
            last_success_at=last_success.finished_at if last_success else None,
            last_operation=last,
            last_error=last if last is not None and last.status == SyncStatus.ERROR else None,
            syncing=self._runner.is_busy(user_id),
        )
