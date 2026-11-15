"""KSK: connecting the user's Google Calendar account and reporting its state (F-24, F-25, F-30).

The service knows the calendar only through the CalendarProvider port (N-41, N-42). OAuth tokens are encrypted
before they are stored and are never logged (N-43).
"""

import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.application.errors import CalendarError
from app.application.ports import CalendarAccountRepository, CalendarProvider, TokenCipher
from app.domain.entities import CalendarAccount, CalendarAccountStatus

log = logging.getLogger(__name__)

STATE_BYTES = 32  # 256 bits, more than the 128 required by N-44


@dataclass(frozen=True)
class ConnectRequest:
    """Redirect the user to `url`; keep `state` and `code_verifier` in their session until the callback."""

    url: str
    state: str
    code_verifier: str


@dataclass(frozen=True)
class CalendarStatusReport:
    """What the calendar window shows (F-30)."""

    status: CalendarAccountStatus
    google_email: str | None = None
    connected_at: datetime | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CalendarSyncService:
    def __init__(
        self,
        provider: CalendarProvider,
        accounts: CalendarAccountRepository,
        cipher: TokenCipher,
        now: Callable[[], datetime] = datetime.now,
        utc_now: Callable[[], datetime] = _utc_now,
    ):
        self._provider = provider
        self._accounts = accounts
        self._cipher = cipher
        self._now = now  # local time, shown to the user (N-29)
        self._utc_now = utc_now  # token expiry is kept in UTC

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

    # ------------------------------------------------------------------ state (F-30)

    def status(self, user_id: int) -> CalendarStatusReport:
        account = self._accounts.get(user_id)
        if account is None:
            return CalendarStatusReport(CalendarAccountStatus.NOT_CONNECTED)
        return CalendarStatusReport(account.status, account.google_email, account.connected_at)
