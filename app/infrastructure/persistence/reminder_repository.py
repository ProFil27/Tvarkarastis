from datetime import date

from app.domain.entities import ReminderSetting, ReminderType
from app.infrastructure.database import Database


class PostgresReminderSettingRepository:
    def __init__(self, database: Database):
        self._db = database

    def get(self, user_id: int) -> ReminderSetting:
        with self._db.cursor() as cur:
            cur.execute("SELECT enabled, closed_period_start FROM reminder_settings WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        return ReminderSetting(user_id, row["enabled"], row["closed_period_start"]) if row else ReminderSetting(user_id)

    def set_enabled(self, user_id: int, enabled: bool) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO reminder_settings (user_id, enabled) VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET enabled = EXCLUDED.enabled
                """,
                (user_id, enabled),
            )

    def set_closed_period(self, user_id: int, period_start: date, reminder_type: ReminderType) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO reminder_settings (user_id, closed_period_start, closed_period_type) VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET closed_period_start = EXCLUDED.closed_period_start, closed_period_type = EXCLUDED.closed_period_type
                """,
                (user_id, period_start, reminder_type.value),
            )
