"""GKK: the Google adapter, tested without network access."""

import os
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from oauthlib.oauth2.rfc6749 import errors as oauth_errors

from app.application.errors import CalendarError
from app.domain.entities import CalendarTokens
from app.infrastructure.calendar import google_calendar_client as gkk
from app.infrastructure.calendar.google_calendar_client import GoogleCalendarClient

REDIRECT = "http://127.0.0.1:5000/calendar/callback"


def make_client(redirect=REDIRECT):
    return GoogleCalendarClient("client-id", "client-secret", redirect)


def test_authorization_url_asks_only_for_the_minimal_scopes_and_uses_pkce():
    request = make_client().authorization_url("my-state")
    query = parse_qs(urlparse(request.url).query)

    assert urlparse(request.url).netloc == "accounts.google.com"
    assert query["state"] == ["my-state"] and query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == [REDIRECT] and query["access_type"] == ["offline"]
    assert set(query["scope"][0].split()) == {
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/calendar.events",  # N-44: nothing broader
    }
    assert query["code_challenge_method"] == ["S256"] and request.code_verifier  # PKCE


def test_configuration_check():
    assert make_client().is_configured()
    assert not GoogleCalendarClient("", "", REDIRECT).is_configured()


def test_plain_http_is_allowed_only_for_the_local_redirect(monkeypatch):
    monkeypatch.delenv("OAUTHLIB_INSECURE_TRANSPORT", raising=False)
    make_client("https://example.com/calendar/callback")
    assert "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ
    make_client("http://localhost:5000/calendar/callback")
    assert os.environ["OAUTHLIB_INSECURE_TRANSPORT"] == "1"
    monkeypatch.delenv("OAUTHLIB_INSECURE_TRANSPORT")


class FailingFlow:
    def __init__(self, error):
        self.error = error
        self.code_verifier = None

    def fetch_token(self, code):
        raise self.error


@pytest.mark.parametrize(
    "error,expected",
    [
        (oauth_errors.AccessDeniedError(), CalendarError.ACCESS_DENIED),
        (oauth_errors.InvalidGrantError(), CalendarError.INVALID_CODE),
        (oauth_errors.InvalidClientError(), CalendarError.INVALID_CODE),
        (requests.ConnectionError("no network"), CalendarError.UNAVAILABLE),
        (requests.Timeout(), CalendarError.UNAVAILABLE),
    ],
)
def test_code_exchange_errors_are_translated(monkeypatch, error, expected):
    client = make_client()
    monkeypatch.setattr(client, "_flow", lambda: FailingFlow(error))

    with pytest.raises(CalendarError) as exc:
        client.exchange_code("the-code", "verifier")

    assert exc.value.code == expected


def test_refresh_errors_are_translated(monkeypatch):
    import google.auth.exceptions

    client = make_client()

    class Creds:
        def __init__(self, error, **kwargs):
            self.error = error

        def refresh(self, request):
            raise self.error

    tokens = CalendarTokens("old", "refresh-1", None)
    for error, expected in [
        (google.auth.exceptions.RefreshError("invalid_grant"), CalendarError.AUTH_EXPIRED),
        (google.auth.exceptions.TransportError("offline"), CalendarError.UNAVAILABLE),
    ]:
        monkeypatch.setattr(gkk, "Credentials", lambda error=error, **kwargs: Creds(error))
        with pytest.raises(CalendarError) as exc:
            client.refresh(tokens)
        assert exc.value.code == expected

    with pytest.raises(CalendarError) as exc:
        client.refresh(CalendarTokens("old", None, None))  # nothing to refresh with
    assert exc.value.code == CalendarError.AUTH_EXPIRED
