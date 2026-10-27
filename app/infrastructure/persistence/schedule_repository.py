from datetime import date

from app.domain.entities import StudyEvent, StudyEventType
from app.domain.weekday import Weekday
from app.infrastructure.database import Database


class PostgresScheduleRepository:
    def __init__(self, database: Database):
        self._db = database

    def add(
        self, user_id: int, pdf_document_id: int | None, valid_from: date, valid_to: date, events: list[StudyEvent]
    ) -> int:
        """Create a schedule with its subjects and study events in one transaction."""
        with self._db.cursor(commit=True) as cur:
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
                        (schedule_id, subject_id, event_type, day_of_week, start_time, end_time, room, is_mandatory)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        schedule_id,
                        subject_ids[event.subject_name],
                        event.event_type.value,
                        event.weekday.value,
                        event.start_time,
                        event.end_time,
                        event.room,
                        event.is_mandatory,
                    ),
                )
        return schedule_id

    def list_study_events(
        self, user_id: int, week_start: date | None = None, week_end: date | None = None
    ) -> list[StudyEvent]:
        query = """
            SELECT se.id, se.event_type, se.day_of_week, se.start_time, se.end_time,
                   se.room, se.is_mandatory, sub.name AS subject_name
            FROM study_events se
            JOIN subjects sub ON sub.id = se.subject_id
            JOIN schedules sc ON sc.id = se.schedule_id
            WHERE sc.user_id = %s
        """
        params: list = [user_id]
        if week_start is not None and week_end is not None:
            query += " AND sc.valid_from <= %s AND sc.valid_to >= %s"
            params += [week_end, week_start]
        query += " ORDER BY se.start_time"

        with self._db.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [
            StudyEvent(
                id=r["id"],
                subject_name=r["subject_name"],
                event_type=StudyEventType(r["event_type"]),
                weekday=Weekday(r["day_of_week"]),
                start_time=r["start_time"],
                end_time=r["end_time"],
                room=r["room"],
                is_mandatory=r["is_mandatory"],
            )
            for r in rows
        ]
