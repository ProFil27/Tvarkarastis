from datetime import date

from app.domain.entities import StudyEvent, StudyEventType, WeekPattern
from app.domain.weekday import Weekday
from app.infrastructure.database import Database


_EVENT_QUERY = """
    SELECT se.id, se.event_type, se.day_of_week, se.start_time, se.end_time,
           se.room, se.is_mandatory, se.week_pattern, se.updated_at, sub.name AS subject_name,
           sc.valid_from, sc.valid_to
    FROM study_events se
    JOIN subjects sub ON sub.id = se.subject_id
    JOIN schedules sc ON sc.id = se.schedule_id
    WHERE sc.user_id = %s
"""


def _to_event(r) -> StudyEvent:
    return StudyEvent(
        id=r["id"],
        subject_name=r["subject_name"],
        event_type=StudyEventType(r["event_type"]),
        weekday=Weekday(r["day_of_week"]),
        start_time=r["start_time"],
        end_time=r["end_time"],
        room=r["room"],
        is_mandatory=r["is_mandatory"],
        valid_from=r["valid_from"],
        valid_to=r["valid_to"],
        week_pattern=WeekPattern(r["week_pattern"]),
        updated_at=r["updated_at"],
    )


def _event_values(schedule_id: int, subject_id: int, event: StudyEvent) -> tuple:
    return (
        schedule_id,
        subject_id,
        event.event_type.value,
        event.weekday.value,
        event.start_time,
        event.end_time,
        event.room,
        event.is_mandatory,
        event.week_pattern.value,
    )


class PostgresScheduleRepository:
    def __init__(self, database: Database):
        self._db = database

    def add(
        self, user_id: int, pdf_document_id: int | None, valid_from: date, valid_to: date, events: list[StudyEvent]
    ) -> int:
        """Create a schedule with its subjects and study events in one transaction."""
        with self._db.cursor(commit=True) as cur:
            return self._insert_schedule(cur, user_id, pdf_document_id, valid_from, valid_to, events)

    def replace_all(
        self, user_id: int, pdf_document_id: int | None, valid_from: date, valid_to: date, events: list[StudyEvent]
    ) -> int:
        """Remove all of the user's schedules and save the new one in one transaction (F-23).

        Subjects, study events and conflicts of the removed schedules disappear with them; links to Google
        Calendar events are kept (see calendar_events) so the calendar sync can delete those events.
        """
        with self._db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM schedules WHERE user_id = %s", (user_id,))
            return self._insert_schedule(cur, user_id, pdf_document_id, valid_from, valid_to, events)

    def count_events(self, user_id: int) -> int:
        with self._db.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS n FROM study_events se JOIN schedules sc ON sc.id = se.schedule_id
                WHERE sc.user_id = %s
                """,
                (user_id,),
            )
            return cur.fetchone()["n"]

    @staticmethod
    def _insert_schedule(
        cur, user_id: int, pdf_document_id: int | None, valid_from: date, valid_to: date, events: list[StudyEvent]
    ) -> int:
        cur.execute(
            """
            INSERT INTO schedules (user_id, pdf_document_id, valid_from, valid_to)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (user_id, pdf_document_id, valid_from, valid_to),
        )
        schedule_id = cur.fetchone()["id"]

        subject_ids: dict[str, int] = {}
        for event in events:
            if event.subject_name not in subject_ids:
                cur.execute(
                    "INSERT INTO subjects (schedule_id, name) VALUES (%s, %s) RETURNING id",
                    (schedule_id, event.subject_name),
                )
                subject_ids[event.subject_name] = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO study_events
                    (schedule_id, subject_id, event_type, day_of_week, start_time, end_time, room, is_mandatory,
                     week_pattern)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                _event_values(schedule_id, subject_ids[event.subject_name], event),
            )
        return schedule_id

    def list_study_events(
        self, user_id: int, week_start: date | None = None, week_end: date | None = None
    ) -> list[StudyEvent]:
        query = _EVENT_QUERY
        params: list = [user_id]
        if week_start is not None and week_end is not None:
            query += " AND sc.valid_from <= %s AND sc.valid_to >= %s"
            params += [week_end, week_start]
        query += " ORDER BY se.start_time"

        with self._db.cursor() as cur:
            cur.execute(query, params)
            return [_to_event(r) for r in cur.fetchall()]

    def last_schedule_date(self, user_id: int) -> date | None:
        with self._db.cursor() as cur:
            cur.execute("SELECT max(created_at)::date AS last_upload FROM schedules WHERE user_id = %s", (user_id,))
            return cur.fetchone()["last_upload"]

    def get_event(self, user_id: int, event_id: int) -> StudyEvent | None:
        with self._db.cursor() as cur:
            cur.execute(_EVENT_QUERY + " AND se.id = %s", (user_id, event_id))
            row = cur.fetchone()
        return _to_event(row) if row else None

    def add_event(self, user_id: int, event: StudyEvent, default_from: date, default_to: date) -> StudyEvent:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "SELECT id FROM schedules WHERE user_id = %s ORDER BY valid_to DESC, id DESC LIMIT 1", (user_id,)
            )
            row = cur.fetchone()
            if row:
                schedule_id = row["id"]
            else:
                cur.execute(
                    "INSERT INTO schedules (user_id, valid_from, valid_to) VALUES (%s, %s, %s) RETURNING id",
                    (user_id, default_from, default_to),
                )
                schedule_id = cur.fetchone()["id"]
            subject_id = self._subject_id(cur, schedule_id, event.subject_name)
            cur.execute(
                """
                INSERT INTO study_events
                    (schedule_id, subject_id, event_type, day_of_week, start_time, end_time, room, is_mandatory,
                     week_pattern)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                _event_values(schedule_id, subject_id, event),
            )
            event_id = cur.fetchone()["id"]
        return self.get_event(user_id, event_id)

    def update_event(self, user_id: int, event_id: int, event: StudyEvent) -> StudyEvent | None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT se.schedule_id, se.subject_id FROM study_events se
                JOIN schedules sc ON sc.id = se.schedule_id
                WHERE se.id = %s AND sc.user_id = %s
                """,
                (event_id, user_id),
            )
            current = cur.fetchone()
            if current is None:
                return None
            subject_id = self._subject_id(cur, current["schedule_id"], event.subject_name)
            cur.execute(
                """
                UPDATE study_events SET subject_id = %s, event_type = %s, day_of_week = %s, start_time = %s,
                    end_time = %s, room = %s, is_mandatory = %s, week_pattern = %s, updated_at = now()
                WHERE id = %s
                """,
                (subject_id, event.event_type.value, event.weekday.value, event.start_time, event.end_time,
                 event.room, event.is_mandatory, event.week_pattern.value, event_id),
            )
            self._drop_unused_subject(cur, current["subject_id"])
        return self.get_event(user_id, event_id)

    def remove_event(self, user_id: int, event_id: int) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                DELETE FROM study_events se USING schedules sc
                WHERE se.id = %s AND se.schedule_id = sc.id AND sc.user_id = %s
                RETURNING se.subject_id
                """,
                (event_id, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return False
            self._drop_unused_subject(cur, row["subject_id"])
            return True

    @staticmethod
    def _subject_id(cur, schedule_id: int, name: str) -> int:
        cur.execute("SELECT id FROM subjects WHERE schedule_id = %s AND name = %s", (schedule_id, name))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("INSERT INTO subjects (schedule_id, name) VALUES (%s, %s) RETURNING id", (schedule_id, name))
        return cur.fetchone()["id"]

    @staticmethod
    def _drop_unused_subject(cur, subject_id: int) -> None:
        cur.execute(
            "DELETE FROM subjects WHERE id = %s AND NOT EXISTS (SELECT 1 FROM study_events WHERE subject_id = %s)",
            (subject_id, subject_id),
        )
