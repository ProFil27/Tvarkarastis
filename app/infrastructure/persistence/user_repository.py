from app.domain.entities import User
from app.infrastructure.database import Database


class PostgresUserRepository:
    def __init__(self, database: Database):
        self._db = database

    def add(self, name: str, email: str, password_hash: str, ai_consent: bool) -> User:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO users (name, email, password_hash, ai_consent) VALUES (%s, %s, %s, %s) RETURNING id",
                (name, email, password_hash, ai_consent),
            )
            user_id = cur.fetchone()["id"]
        return User(user_id, name, email, password_hash, ai_consent)

    def get_by_email(self, email: str) -> User | None:
        with self._db.cursor() as cur:
            cur.execute("SELECT id, name, email, password_hash, ai_consent FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
        return User(**row) if row else None
