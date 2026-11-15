"""Connecting a Google Calendar account (F-24, F-25, N-43, N-44, N-46, US-11)."""

import base64
import logging
from datetime import datetime

import pytest
from cryptography.fernet import Fernet

from app.application.calendar_sync_service import CalendarSyncService
from app.application.errors import CalendarError
from app.container import Services
from app.domain.entities import CalendarAccountStatus
from app.infrastructure.security import FernetTokenCipher
from app.web import create_app
from tests import fakes

NOW = datetime(2026, 11, 14, 10, 12)


def make_service(provider=None, cipher=None):
    provider = provider or fakes.FakeCalendarProvider()
    accounts = fakes.FakeCalendarAccountRepository()
    service = CalendarSyncService(
        provider, accounts, cipher or fakes.FakeTokenCipher(), now=lambda: NOW, utc_now=lambda: NOW
    )
    return service, provider, accounts


def code_of(exc_info):
    return exc_info.value.code


def test_connect_needs_consent_and_a_configured_integration():
    with pytest.raises(CalendarError) as exc:
        make_service()[0].begin_connect(1, consent_given=False)
    assert code_of(exc) == CalendarError.CONSENT_REQUIRED

    with pytest.raises(CalendarError) as exc:
        make_service(provider=fakes.FakeCalendarProvider(configured=False))[0].begin_connect(1, True)
    assert code_of(exc) == CalendarError.NOT_CONFIGURED

    with pytest.raises(CalendarError) as exc:
        make_service(cipher=fakes.FakeTokenCipher(available=False))[0].begin_connect(1, True)
    assert code_of(exc) == CalendarError.NOT_CONFIGURED


def test_state_is_random_and_at_least_128_bits():
    service, provider, _ = make_service()
    first, second = service.begin_connect(1, True), service.begin_connect(1, True)

    assert first.state != second.state
    padded = first.state + "=" * (-len(first.state) % 4)
    assert len(base64.urlsafe_b64decode(padded)) * 8 >= 128  # N-44
    assert first.url == f"https://accounts.example.com/auth?state={first.state}"
    assert first.code_verifier == "verifier-1"


def test_successful_connection_stores_encrypted_tokens_and_the_connected_status():
    service, provider, accounts = make_service()
    request = service.begin_connect(1, True)

    account = service.complete_connect(1, "the-code", request.state, request.state, request.code_verifier)

    assert provider.calls[-1] == ("exchange_code", "the-code", "verifier-1")
    assert account.status == CalendarAccountStatus.CONNECTED and account.google_email == "student@gmail.com"
    assert account.access_token_enc == "enc:access-1" and account.refresh_token_enc == "enc:refresh-1"  # never plain
    assert account.connected_at == NOW and account.consent_given_at == NOW
    assert service.status(1).google_email == "student@gmail.com"
    assert service.status(1).connected_at == NOW


@pytest.mark.parametrize(
    "kwargs,provider_errors,expected",
    [
        ({"error": "access_denied", "code": None}, {}, CalendarError.ACCESS_DENIED),
        ({"error": "server_error", "code": None}, {}, CalendarError.INVALID_CODE),
        ({"state": "forged"}, {}, CalendarError.INVALID_STATE),
        ({"state": None}, {}, CalendarError.INVALID_STATE),
        ({"expected_state": None}, {}, CalendarError.INVALID_STATE),
        ({"code": None}, {}, CalendarError.INVALID_CODE),
        ({}, {"exchange_code": CalendarError(CalendarError.INVALID_CODE)}, CalendarError.INVALID_CODE),
        ({}, {"exchange_code": CalendarError(CalendarError.UNAVAILABLE)}, CalendarError.UNAVAILABLE),
    ],
)
def test_failed_connection_stores_nothing_and_keeps_the_account_disconnected(kwargs, provider_errors, expected):
    service, provider, accounts = make_service(fakes.FakeCalendarProvider(errors=provider_errors))
    request = service.begin_connect(1, True)
    arguments = {"code": "c", "state": request.state, "expected_state": request.state,
                 "code_verifier": request.code_verifier, "error": None, **kwargs}

    with pytest.raises(CalendarError) as exc:
        service.complete_connect(1, **arguments)

    assert code_of(exc) == expected
    assert accounts.accounts == {}  # no tokens stored
    assert service.status(1).status == CalendarAccountStatus.NOT_CONNECTED


def test_a_failed_reconnect_does_not_change_an_account_that_needs_reconnecting():
    service, provider, accounts = make_service(fakes.FakeCalendarProvider(
        errors={"exchange_code": CalendarError(CalendarError.UNAVAILABLE)}))
    accounts.save_connected(1, "a@b.lt", "enc:x", "enc:y", None, NOW, NOW)
    accounts.set_status(1, CalendarAccountStatus.RECONNECT_REQUIRED)
    request = service.begin_connect(1, True)

    with pytest.raises(CalendarError):
        service.complete_connect(1, "c", request.state, request.state, request.code_verifier)

    assert accounts.get(1).status == CalendarAccountStatus.RECONNECT_REQUIRED and accounts.get(1).access_token_enc == "enc:x"


def test_tokens_are_never_written_to_the_log(caplog):
    caplog.set_level(logging.DEBUG)
    service, provider, _ = make_service()
    request = service.begin_connect(1, True)
    service.complete_connect(1, "the-code", request.state, request.state, request.code_verifier)
    with pytest.raises(CalendarError):
        service.complete_connect(1, "the-code", "forged", request.state, request.code_verifier)

    assert "access-1" not in caplog.text and "refresh-1" not in caplog.text and request.state not in caplog.text


def test_fernet_cipher_round_trip_and_wrong_key():
    key = Fernet.generate_key().decode()
    cipher = FernetTokenCipher(key)
    secret = "ya29.a0-secret-token"

    encrypted = cipher.encrypt(secret)
    assert cipher.available and encrypted != secret and secret not in encrypted
    assert cipher.decrypt(encrypted) == secret

    with pytest.raises(CalendarError) as exc:
        FernetTokenCipher(Fernet.generate_key().decode()).decrypt(encrypted)
    assert code_of(exc) == CalendarError.AUTH_EXPIRED
    with pytest.raises(CalendarError) as exc:
        cipher.decrypt("demo-not-a-real-token")  # e.g. the placeholder tokens of the demo data
    assert code_of(exc) == CalendarError.AUTH_EXPIRED


@pytest.mark.parametrize("key", ["", "not-a-fernet-key"])
def test_cipher_without_a_valid_key_is_unavailable_and_does_not_crash_the_app(key):
    cipher = FernetTokenCipher(key)
    assert cipher.available is False
    with pytest.raises(CalendarError) as exc:
        cipher.encrypt("x")
    assert code_of(exc) == CalendarError.NOT_CONFIGURED


def make_client(provider=None, cipher=None, user_id=1):
    service, provider, accounts = make_service(provider, cipher)
    client = create_app(services=Services(calendar=service)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client, provider, accounts


def test_calendar_page_requires_login():
    client = create_app(services=Services(calendar=make_service()[0])).test_client()
    assert client.get("/calendar/").status_code == 302


def test_calendar_page_when_not_connected_shows_the_consent_text_and_the_connect_button():
    client, _, _ = make_client()
    page = client.get("/calendar/").get_data(as_text=True)

    assert "Neprijungta" in page and "Prijungti Google Calendar" in page
    assert "dalykas, įvykio tipas, laikas, auditorija ir darbovietė būtų siunčiami į Google Calendar" in page
    assert "nesukonfigūruota" not in page


def test_calendar_page_explains_when_the_integration_is_not_configured():
    client, _, _ = make_client(provider=fakes.FakeCalendarProvider(configured=False))
    assert "nesukonfigūruota" in client.get("/calendar/").get_data(as_text=True)


def test_connect_without_consent_shows_a_message_and_does_not_leave_the_site():
    client, provider, _ = make_client()
    response = client.post("/calendar/connect", follow_redirects=True)
    assert "patvirtinkite sutikimą siųsti duomenis į Google" in response.get_data(as_text=True)
    assert provider.calls == []


def full_connect(client, **callback_args):
    response = client.post("/calendar/connect", data={"consent": "on"})
    state = response.headers["Location"].split("state=")[1]
    return response, state, client.get("/calendar/callback", query_string={"code": "c", "state": state, **callback_args},
                                       follow_redirects=True)


def test_connect_redirects_to_google_and_the_callback_finishes_the_connection():
    client, provider, accounts = make_client()

    response, state, callback = full_connect(client)

    assert response.status_code == 302 and response.headers["Location"].startswith("https://accounts.example.com/auth")
    page = callback.get_data(as_text=True)
    assert "Google Calendar prijungtas." in page and "student@gmail.com" in page and "Prijungta" in page
    assert "prijungta 2026-" in page  # date and time in YYYY-MM-DD HH:MM
    assert accounts.get(1).status == CalendarAccountStatus.CONNECTED


def test_callback_rejects_a_wrong_state_and_the_state_cannot_be_reused():
    client, provider, accounts = make_client()
    client.post("/calendar/connect", data={"consent": "on"})

    forged = client.get("/calendar/callback", query_string={"code": "c", "state": "forged"}, follow_redirects=True)
    assert "Neteisingas užklausos kodas" in forged.get_data(as_text=True) and accounts.accounts == {}

    # The real state was used up by the failed attempt: the flow has to be started again.
    response = client.post("/calendar/connect", data={"consent": "on"})
    state = response.headers["Location"].split("state=")[1]
    ok = client.get("/calendar/callback", query_string={"code": "c", "state": state})
    assert ok.status_code == 302 and accounts.get(1) is not None
    replay = client.get("/calendar/callback", query_string={"code": "c", "state": state}, follow_redirects=True)
    assert "Neteisingas užklausos kodas" in replay.get_data(as_text=True)


@pytest.mark.parametrize(
    "provider_errors,callback_args,message",
    [
        ({}, {"error": "access_denied"}, "Prieiga nepatvirtinta. Kalendorius neprijungtas."),
        ({"exchange_code": CalendarError(CalendarError.INVALID_CODE)}, {}, "Neteisingas užklausos kodas"),
        ({"exchange_code": CalendarError(CalendarError.UNAVAILABLE)}, {}, "Kalendoriaus tiekėjas nepasiekiamas. Bandykite dar kartą."),
    ],
)
def test_connection_failures_show_the_reason_and_leave_the_account_disconnected(provider_errors, callback_args, message):
    client, provider, accounts = make_client(provider=fakes.FakeCalendarProvider(errors=provider_errors))

    _, _, callback = full_connect(client, **callback_args)

    page = callback.get_data(as_text=True)
    assert message in page and "Neprijungta" in page and accounts.accounts == {}


def test_reminder_switch_in_the_calendar_window():
    from app.application.reminder_service import ReminderService

    reminders = ReminderService(fakes.FakeReminderSettingRepository(), fakes.FakeScheduleRepository(), [(9, 1)])
    service, _, _ = make_service()
    client = create_app(services=Services(calendar=service, reminders=reminders)).test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1

    assert "Įjungta" in client.get("/calendar/").get_data(as_text=True)
    client.post("/calendar/reminders", data={})  # unchecked switch -> disable
    assert reminders.is_enabled(1) is False and "Išjungta" in client.get("/calendar/").get_data(as_text=True)
    client.post("/calendar/reminders", data={"enabled": "on"})
    assert reminders.is_enabled(1) is True
