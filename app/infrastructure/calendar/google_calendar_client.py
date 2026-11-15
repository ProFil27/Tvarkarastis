"""GKK: the only module that talks to Google OAuth 2.0 and the Google Calendar API (N-28, N-41, N-42).

Every other component reaches the calendar service through the CalendarProvider port, so replacing Google with
another calendar means replacing this module only.
"""

import logging
import os
from datetime import datetime
from urllib.parse import urlparse

import google.auth.exceptions
import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2.rfc6749 import errors as oauth_errors

from app.application.errors import CalendarError
from app.application.ports import AuthorizationRequest
from app.domain.entities import CalendarTokens

log = logging.getLogger(__name__)

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
# Minimal access (N-44): calendar events and the account's e-mail address only.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.events",
]

# Google may return the scopes in another order or with short aliases; do not treat that as an error.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


class GoogleCalendarClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
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
            credentials.token, credentials.refresh_token, credentials.expiry, self._email(credentials.id_token)
        )

    def _email(self, token: str | None) -> str | None:
        """The Google account's e-mail from the verified ID token; None if it cannot be read."""
        if not token:
            return None
        try:
            return id_token.verify_oauth2_token(token, Request(), self._client_id).get("email")
        except (ValueError, google.auth.exceptions.GoogleAuthError) as exc:
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
