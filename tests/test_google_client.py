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


# ----------------------------------------------------------------------------- events and retries (N-31)

import httplib2  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402

TOKENS = CalendarTokens("access-1", "refresh-1", None)


def http_error(status, content=b"{}"):
    return HttpError(httplib2.Response({"status": status}), content)


class FakeRequest:
    def __init__(self, outcomes, result):
        self.outcomes, self.result = outcomes, result

    def execute(self, num_retries=0):
        assert num_retries == 0  # retries are ours, so that the waiting times are exactly 1, 2 and 4 seconds
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return self.result


class FakeCalendarApi:
    """Mimics service.events().insert/update/delete(...) and records the number of attempts."""

    def __init__(self, outcomes, result=None):
        self.outcomes, self.result, self.attempts, self.requests = outcomes, result or {"id": "g1"}, 0, []

    def events(self):
        return self

    def _request(self, kind, **kwargs):
        self.requests.append((kind, kwargs))
        api = self

        class Counted(FakeRequest):
            def execute(self, num_retries=0):
                api.attempts += 1
                return super().execute(num_retries)

        return Counted(self.outcomes, self.result)

    def insert(self, **kwargs):
        return self._request("insert", **kwargs)

    def update(self, **kwargs):
        return self._request("update", **kwargs)

    def delete(self, **kwargs):
        return self._request("delete", **kwargs)


def client_with(api, monkeypatch):
    sleeps = []
    client = GoogleCalendarClient("id", "secret", REDIRECT, sleep=sleeps.append)
    monkeypatch.setattr(client, "_service", lambda tokens: api)
    return client, sleeps


def test_create_event_sends_the_body_to_the_primary_calendar_and_returns_the_google_id(monkeypatch):
    api = FakeCalendarApi([None], {"id": "abc123"})
    client, sleeps = client_with(api, monkeypatch)

    assert client.create_event(TOKENS, {"summary": "Paskaita"}) == "abc123"
    assert api.requests == [("insert", {"calendarId": "primary", "body": {"summary": "Paskaita"}})]
    assert sleeps == []


@pytest.mark.parametrize("failure", [http_error(503), http_error(500), http_error(429), requests.ConnectionError("x"),
                                     TimeoutError("slow"), http_error(403, b'{"errors":[{"reason":"rateLimitExceeded"}]}')])
def test_temporary_failures_are_retried_after_1_2_and_4_seconds(monkeypatch, failure):
    api = FakeCalendarApi([failure, failure, failure, None])
    client, sleeps = client_with(api, monkeypatch)

    assert client.create_event(TOKENS, {}) == "g1"
    assert sleeps == [1, 2, 4] and api.attempts == 4


def test_after_three_retries_the_error_is_reported_as_unavailable(monkeypatch):
    api = FakeCalendarApi([http_error(503)] * 4)
    client, sleeps = client_with(api, monkeypatch)

    with pytest.raises(CalendarError) as exc:
        client.create_event(TOKENS, {})

    assert exc.value.code == CalendarError.UNAVAILABLE and sleeps == [1, 2, 4] and api.attempts == 4  # at most 3 retries


@pytest.mark.parametrize(
    "status,content,expected",
    [(401, b"{}", CalendarError.AUTH_EXPIRED), (400, b"{}", CalendarError.REJECTED),
     (403, b'{"errors":[{"reason":"forbidden"}]}', CalendarError.REJECTED), (404, b"{}", CalendarError.NOT_FOUND)],
)
def test_permanent_errors_are_not_retried(monkeypatch, status, content, expected):
    api = FakeCalendarApi([http_error(status, content)])
    client, sleeps = client_with(api, monkeypatch)

    with pytest.raises(CalendarError) as exc:
        client.update_event(TOKENS, "g1", {})

    assert exc.value.code == expected and sleeps == [] and api.attempts == 1
    assert api.requests[0] == ("update", {"calendarId": "primary", "eventId": "g1", "body": {}})


def test_deleting_an_event_that_is_already_gone_succeeds_but_other_errors_do_not(monkeypatch):
    client, _ = client_with(FakeCalendarApi([http_error(404)]), monkeypatch)
    client.delete_event(TOKENS, "g1")  # no exception

    client, _ = client_with(FakeCalendarApi([http_error(401)]), monkeypatch)
    with pytest.raises(CalendarError) as exc:
        client.delete_event(TOKENS, "g1")
    assert exc.value.code == CalendarError.AUTH_EXPIRED
