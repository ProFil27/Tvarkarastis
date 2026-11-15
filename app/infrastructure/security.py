"""Security adapters: password hashing (N-20) and token encryption (N-43)."""

import logging

from cryptography.fernet import Fernet, InvalidToken
from werkzeug.security import check_password_hash, generate_password_hash

from app.application.errors import CalendarError

log = logging.getLogger(__name__)


class WerkzeugPasswordHasher:
    def hash(self, password: str) -> str:
        return generate_password_hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return check_password_hash(password_hash, password)


class FernetTokenCipher:
    """Symmetric encryption of OAuth tokens stored in the database (N-43). The key comes from the configuration."""

    def __init__(self, key: str):
        self._fernet = None
        if key:
            try:
                self._fernet = Fernet(key.encode())
            except ValueError:
                log.error("TOKEN_ENCRYPTION_KEY is not a valid Fernet key; calendar tokens cannot be stored")

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, plain_text: str) -> str:
        if self._fernet is None:
            raise CalendarError(CalendarError.NOT_CONFIGURED, "No valid TOKEN_ENCRYPTION_KEY")
        return self._fernet.encrypt(plain_text.encode()).decode()

    def decrypt(self, cipher_text: str) -> str:
        if self._fernet is None:
            raise CalendarError(CalendarError.NOT_CONFIGURED, "No valid TOKEN_ENCRYPTION_KEY")
        try:
            return self._fernet.decrypt(cipher_text.encode()).decode()
        except InvalidToken:
            raise CalendarError(CalendarError.AUTH_EXPIRED, "Stored calendar tokens cannot be decrypted")
