from datetime import datetime

from app.domain.entities import CalendarAccount, CalendarAccountStatus
from app.infrastructure.database import Database


class PostgresCalendarAccountRepository:
    def __init__(self, database: Database):
        self._db = database

    def get(self, user_id: int) -> CalendarAccount | None:
        with self._db.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, google_email, access_token_enc, refresh_token_enc, token_expires_at,
                       consent_given_at, connected_at, status
                FROM calendar_accounts WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return CalendarAccount(
            user_id=row["user_id"],
            status=CalendarAccountStatus(row["status"]),
            google_email=row["google_email"],
            access_token_enc=row["access_token_enc"],
            refresh_token_enc=row["refresh_token_enc"],
            token_expires_at=row["token_expires_at"],
            consent_given_at=row["consent_given_at"],
            connected_at=row["connected_at"],
        )

    def save_connected(
        self,
        user_id: int,
        google_email: str | None,
        access_token_enc: str,
        refresh_token_enc: str | None,
        token_expires_at: datetime | None,
        consent_given_at: datetime,
        connected_at: datetime,
    ) -> CalendarAccount:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO calendar_accounts
                    (user_id, google_email, access_token_enc, refresh_token_enc, token_expires_at,
                     consent_given_at, connected_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    google_email = EXCLUDED.google_email, access_token_enc = EXCLUDED.access_token_enc,
                    refresh_token_enc = EXCLUDED.refresh_token_enc, token_expires_at = EXCLUDED.token_expires_at,
                    consent_given_at = EXCLUDED.consent_given_at, connected_at = EXCLUDED.connected_at,
                    status = EXCLUDED.status
                """,
                (
                    user_id,
                    google_email,
                    access_token_enc,
                    refresh_token_enc,
                    token_expires_at,
                    consent_given_at,
                    connected_at,
                    CalendarAccountStatus.CONNECTED.value,
                ),
            )
        return self.get(user_id)

    def update_tokens(
        self, user_id: int, access_token_enc: str, refresh_token_enc: str | None, token_expires_at: datetime | None
    ) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE calendar_accounts SET access_token_enc = %s, token_expires_at = %s,
                    refresh_token_enc = COALESCE(%s, refresh_token_enc)
                WHERE user_id = %s
                """,
                (access_token_enc, token_expires_at, refresh_token_enc, user_id),
            )

    def set_status(self, user_id: int, status: CalendarAccountStatus) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute("UPDATE calendar_accounts SET status = %s WHERE user_id = %s", (status.value, user_id))
