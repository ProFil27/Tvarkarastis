from datetime import time

from app.domain.entities import WorkShift
from app.domain.weekday import Weekday
from app.infrastructure.database import Database


class PostgresWorkShiftRepository:
    def __init__(self, database: Database):
        self._db = database

    def add(self, user_id: int, workplace_name: str, weekday: Weekday, start_time: time, end_time: time) -> WorkShift:
        with self._db.cursor(commit=True) as cur:
            cur.execute("SELECT id FROM workplaces WHERE user_id = %s AND name = %s", (user_id, workplace_name))
            row = cur.fetchone()
            if row:
                workplace_id = row["id"]
            else:
                cur.execute(
                    "INSERT INTO workplaces (user_id, name) VALUES (%s, %s) RETURNING id", (user_id, workplace_name)
                )
                workplace_id = cur.fetchone()["id"]

            cur.execute(
                """
                INSERT INTO work_shifts (workplace_id, day_of_week, start_time, end_time)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (workplace_id, weekday.value, start_time, end_time),
            )
            shift_id = cur.fetchone()["id"]
        return WorkShift(shift_id, workplace_name, weekday, start_time, end_time)

    def list_for_user(self, user_id: int) -> list[WorkShift]:
        with self._db.cursor() as cur:
            cur.execute(
                """
                SELECT ws.id, ws.day_of_week, ws.start_time, ws.end_time, w.name AS workplace_name
                FROM work_shifts ws
                JOIN workplaces w ON w.id = ws.workplace_id
                WHERE w.user_id = %s
                ORDER BY ws.start_time
                """,
                (user_id,),
            )
            rows = cur.fetchall()
        return [
            WorkShift(r["id"], r["workplace_name"], Weekday(r["day_of_week"]), r["start_time"], r["end_time"])
            for r in rows
        ]

    def remove(self, user_id: int, shift_id: int) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                DELETE FROM work_shifts ws
                USING workplaces w
                WHERE ws.id = %s AND ws.workplace_id = w.id AND w.user_id = %s
                """,
                (shift_id, user_id),
            )
            return cur.rowcount > 0
