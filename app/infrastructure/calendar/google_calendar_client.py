"""GKK: the only module that talks to Google OAuth 2.0 and the Google Calendar API (N-28, N-41, N-42).

Every other component reaches the calendar service through the CalendarProvider port, so replacing Google with
another calendar means replacing this module only.
"""

import logging
import os
import threading
import time
from datetime import datetime
from typing import Callable
from urllib.parse import urlparse

import google.auth.exceptions
import httplib2
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauthlib.oauth2.rfc6749 import errors as oauth_errors

from app.application.errors import CalendarError
from app.application.ports import AuthorizationRequest
from app.domain.entities import CalendarTokens
from app.domain.rules import SYNC_RETRY_DELAYS

log = logging.getLogger(__name__)

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
USERINFO_URI = "https://openidconnect.googleapis.com/v1/userinfo"
# Minimal access (N-44): calendar events and the account's e-mail address only.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events",
]

# Google may return the scopes in another order or with short aliases; do not treat that as an error.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


class GoogleCalendarClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        sleep: Callable[[float], None] = time.sleep,
        retry_delays: tuple[float, ...] = SYNC_RETRY_DELAYS,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._sleep = sleep
        self._retry_delays = retry_delays
        # The API client is not thread-safe: every thread keeps its own (access token -> client).
        self._local = threading.local()
        host = urlparse(redirect_uri).hostname
        if redirect_uri.startswith("http://") and host in ("127.0.0.1", "localhost"):
            # The local prototype is reached over plain http on this computer only (N-27).
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret and self._redirect_uri)

    def _flow(self) -> Flow:
        config = {
            "web": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "auth_uri": AUTH_URI,
                "token_uri": TOKEN_URI,
                "redirect_uris": [self._redirect_uri],
            }
        }
        return Flow.from_client_config(config, scopes=SCOPES, redirect_uri=self._redirect_uri)

    def authorization_url(self, state: str) -> AuthorizationRequest:
        flow = self._flow()
        url, _ = flow.authorization_url(state=state, access_type="offline", prompt="consent")
        return AuthorizationRequest(url, flow.code_verifier)

    def exchange_code(self, code: str, code_verifier: str) -> CalendarTokens:
        flow = self._flow()
        flow.code_verifier = code_verifier
        try:
            flow.fetch_token(code=code)
        except oauth_errors.AccessDeniedError:
            raise CalendarError(CalendarError.ACCESS_DENIED)
        except oauth_errors.OAuth2Error as exc:
            raise CalendarError(CalendarError.INVALID_CODE, type(exc).__name__)
        except (requests.RequestException, OSError) as exc:
            raise CalendarError(CalendarError.UNAVAILABLE, type(exc).__name__)

        credentials = flow.credentials
        return CalendarTokens(
            credentials.token, credentials.refresh_token, credentials.expiry, self._email(credentials.token)
        )

    @staticmethod
    def _email(access_token: str) -> str | None:
        """The Google account's e-mail address (scope userinfo.email); None if it cannot be read.

        Asking Google with the access token is more robust than verifying the ID token locally, which fails when the
        computer's clock is a few seconds off.
        """
        try:
            response = requests.get(
                USERINFO_URI, headers={"Authorization": f"Bearer {access_token}"}, timeout=10
            )
            response.raise_for_status()
            return response.json().get("email")
        except (requests.RequestException, ValueError) as exc:
            log.warning("Could not read the Google account e-mail: %s", type(exc).__name__)
            return None

    def refresh(self, tokens: CalendarTokens) -> CalendarTokens:
        if not tokens.refresh_token:
            raise CalendarError(CalendarError.AUTH_EXPIRED, "No refresh token")
        credentials = Credentials(
            token=None,
            refresh_token=tokens.refresh_token,
            token_uri=TOKEN_URI,
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        try:
            credentials.refresh(Request())
        except google.auth.exceptions.RefreshError:
            raise CalendarError(CalendarError.AUTH_EXPIRED, "The refresh token was rejected")
        except (google.auth.exceptions.TransportError, requests.RequestException, OSError) as exc:
            raise CalendarError(CalendarError.UNAVAILABLE, type(exc).__name__)
        expires_at: datetime | None = credentials.expiry
        return CalendarTokens(credentials.token, tokens.refresh_token, expires_at, tokens.email)

    # ------------------------------------------------------------------ events (F-26, F-28, F-29)

    def _service(self, tokens: CalendarTokens):
        services = getattr(self._local, "services", None)
        if services is None:
            services = self._local.services = {}
        service = services.get(tokens.access_token)
        if service is None:
            services.clear()  # keep at most one client per thread; older tokens are no longer used
            service = build(
                "calendar", "v3", credentials=Credentials(token=tokens.access_token), cache_discovery=False
            )
            services[tokens.access_token] = service
        return service

    def create_event(self, tokens: CalendarTokens, body: dict) -> str:
        result = self._execute(lambda: self._service(tokens).events().insert(calendarId="primary", body=body))
        return result["id"]

    def update_event(self, tokens: CalendarTokens, google_event_id: str, body: dict) -> None:
        self._execute(
            lambda: self._service(tokens).events().update(calendarId="primary", eventId=google_event_id, body=body)
        )

    def delete_event(self, tokens: CalendarTokens, google_event_id: str) -> None:
        try:
            self._execute(
                lambda: self._service(tokens).events().delete(calendarId="primary", eventId=google_event_id)
            )
        except CalendarError as exc:
            if exc.code != CalendarError.NOT_FOUND:  # already deleted in Google: nothing left to do
                raise

    def _execute(self, make_request):
        """Run one API request; network errors, HTTP 5xx and 429 are retried after 1 s, 2 s and 4 s (N-31)."""
        for attempt in range(len(self._retry_delays) + 1):
            try:
                return make_request().execute(num_retries=0)
            except HttpError as exc:
                code, retryable = _classify_http_error(exc)
                reason = f"HTTP {exc.resp.status}: {exc.reason}"  # Google's explanation; never contains tokens
                if not retryable:
                    log.warning("Calendar request rejected: %s", reason)
                    raise CalendarError(code, reason)
            except (OSError, httplib2.HttpLib2Error, google.auth.exceptions.TransportError) as exc:
                reason = type(exc).__name__
            if attempt < len(self._retry_delays):
                log.warning("Calendar request failed (%s); retrying in %s s", reason, self._retry_delays[attempt])
                self._sleep(self._retry_delays[attempt])
        raise CalendarError(CalendarError.UNAVAILABLE, reason)


def _classify_http_error(exc: HttpError) -> tuple[str, bool]:
    """(CalendarError code, retryable) for an HTTP error from the Calendar API (GKK-3)."""
    status = exc.resp.status
    if status == 429 or status >= 500:
        return CalendarError.UNAVAILABLE, True
    if status == 403 and (b"rateLimitExceeded" in exc.content or b"userRateLimitExceeded" in exc.content):
        return CalendarError.UNAVAILABLE, True
    if status == 401:
        return CalendarError.AUTH_EXPIRED, False
    if status in (404, 410):
        return CalendarError.NOT_FOUND, False
    return CalendarError.REJECTED, False
