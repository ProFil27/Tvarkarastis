from datetime import datetime

from app.domain.entities import CalendarEventLink
from app.infrastructure.database import Database


class PostgresCalendarEventRepository:
    def __init__(self, database: Database):
        self._db = database

    def list_links(self, user_id: int) -> list[CalendarEventLink]:
        with self._db.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, study_event_id, work_shift_id, shift_series_id, google_event_id, synced_at
                FROM calendar_events WHERE user_id = %s ORDER BY id
                """,
                (user_id,),
            )
            return [CalendarEventLink(**row) for row in cur.fetchall()]

    def add_link(
        self,
        user_id: int,
        study_event_id: int | None,
        work_shift_id: int | None,
        google_event_id: str,
        synced_at: datetime,
        shift_series_id: int | None = None,
    ) -> CalendarEventLink:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO calendar_events
                    (user_id, study_event_id, work_shift_id, shift_series_id, google_event_id, synced_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, user_id, study_event_id, work_shift_id, shift_series_id, google_event_id, synced_at
                """,
                (user_id, study_event_id, work_shift_id, shift_series_id, google_event_id, synced_at),
            )
            return CalendarEventLink(**cur.fetchone())

    def touch_link(self, link_id: int, synced_at: datetime) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute("UPDATE calendar_events SET synced_at = %s WHERE id = %s", (synced_at, link_id))

    def replace_google_event(self, link_id: int, google_event_id: str, synced_at: datetime) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE calendar_events SET google_event_id = %s, synced_at = %s WHERE id = %s",
                (google_event_id, synced_at, link_id),
            )

    def remove_link(self, link_id: int) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM calendar_events WHERE id = %s", (link_id,))
