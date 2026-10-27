"""Registration and authentication (F-01, F-02)."""

import re

from app.application.errors import ValidationFailed
from app.application.ports import PasswordHasher, UserRepository
from app.domain.entities import User
from app.domain.rules import MIN_PASSWORD_LENGTH

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthService:
    def __init__(self, users: UserRepository, hasher: PasswordHasher):
        self._users = users
        self._hasher = hasher

    def register(self, name: str, email: str, password: str, ai_consent: bool) -> User:
        errors = self._validate_registration(name, email, password)
        if errors:
            raise ValidationFailed(errors)
        return self._users.add(
            name=name.strip(),
            email=email.strip().lower(),
            password_hash=self._hasher.hash(password),
            ai_consent=ai_consent,
        )

    def authenticate(self, email: str, password: str) -> User | None:
        """Return the user for valid credentials, otherwise None."""
        if not email or not password:
            return None
        user = self._users.get_by_email(email.strip().lower())
        if user is None or not self._hasher.verify(password, user.password_hash):
            return None
        return user

    def _validate_registration(self, name: str, email: str, password: str) -> dict[str, str]:
        errors: dict[str, str] = {}
        if not name or not name.strip():
            errors["name"] = "required"

        if not email or not email.strip():
            errors["email"] = "required"
        elif not _EMAIL_PATTERN.match(email.strip()):
            errors["email"] = "invalid_format"
        elif self._users.get_by_email(email.strip().lower()) is not None:
            errors["email"] = "already_registered"

        if not password:
            errors["password"] = "required"
        elif len(password) < MIN_PASSWORD_LENGTH:
            errors["password"] = "too_short"
        return errors
