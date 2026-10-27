import pytest

from app.application.auth_service import AuthService
from app.application.errors import ValidationFailed
from app.container import Services
from app.web import create_app
from tests import fakes


def make_auth():
    return AuthService(fakes.FakeUserRepository(), fakes.FakeHasher())


def test_register_hashes_password_and_normalizes_email():
    user = make_auth().register("Jonas", " Jonas@Example.com ", "Slaptazodis123", True)
    assert user.email == "jonas@example.com"
    assert user.password_hash == "hashed:Slaptazodis123"


@pytest.mark.parametrize(
    "name,email,password,expected",
    [
        ("", "a@b.lt", "Slaptazodis123", {"name": "required"}),
        ("J", "bad", "Slaptazodis123", {"email": "invalid_format"}),
        ("J", "a@b.lt", "short", {"password": "too_short"}),
    ],
)
def test_register_validation_codes(name, email, password, expected):
    with pytest.raises(ValidationFailed) as exc:
        make_auth().register(name, email, password, False)
    assert exc.value.errors == expected


def test_register_rejects_duplicate_email_and_login_works():
    auth = make_auth()
    auth.register("Jonas", "a@b.lt", "Slaptazodis123", False)
    with pytest.raises(ValidationFailed) as exc:
        auth.register("Kitas", "a@b.lt", "Slaptazodis123", False)
    assert exc.value.errors == {"email": "already_registered"}
    assert auth.authenticate("a@b.lt", "Slaptazodis123") is not None
    assert auth.authenticate("a@b.lt", "wrong") is None


def test_register_login_logout_over_http_with_lithuanian_messages():
    client = create_app(services=Services(auth=make_auth())).test_client()

    response = client.post("/register", data={"name": "J", "email": "bad", "password": "short"})
    assert "Neteisingas el. pašto formatas" in response.get_data(as_text=True)

    ok = {"name": "Jonas", "email": "j@x.lt", "password": "Slaptazodis123"}
    assert client.post("/register", data=ok).status_code == 302
    client.post("/logout")

    wrong = client.post("/login", data={"email": "j@x.lt", "password": "wrong"})
    assert "Neteisingas el. paštas arba slaptažodis" in wrong.get_data(as_text=True)
    assert client.post("/login", data={"email": "j@x.lt", "password": "Slaptazodis123"}).status_code == 302
