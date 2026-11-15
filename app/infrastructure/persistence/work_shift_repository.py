from datetime import date, time

from app.domain.entities import WorkShift
from app.infrastructure.database import Database


_SHIFT_COLUMNS = "ws.id, ws.work_date, ws.start_time, ws.end_time, ws.updated_at, w.name AS workplace_name"


def _to_shift(r) -> WorkShift:
    return WorkShift(r["id"], r["workplace_name"], r["work_date"], r["start_time"], r["end_time"], r["updated_at"])


class PostgresWorkShiftRepository:
    def __init__(self, database: Database):
        self._db = database

    @staticmethod
    def _workplace_id(cur, user_id: int, workplace_name: str) -> int:
        cur.execute("SELECT id FROM workplaces WHERE user_id = %s AND name = %s", (user_id, workplace_name))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("INSERT INTO workplaces (user_id, name) VALUES (%s, %s) RETURNING id", (user_id, workplace_name))
        return cur.fetchone()["id"]

    def add(self, user_id: int, workplace_name: str, work_date: date, start_time: time, end_time: time) -> WorkShift:
        with self._db.cursor(commit=True) as cur:
            workplace_id = self._workplace_id(cur, user_id, workplace_name)

            cur.execute(
                """
                INSERT INTO work_shifts (workplace_id, work_date, start_time, end_time)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (workplace_id, work_date, start_time, end_time),
            )
            shift_id = cur.fetchone()["id"]
        return self.get(user_id, shift_id)

    def get(self, user_id: int, shift_id: int) -> WorkShift | None:
        with self._db.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SHIFT_COLUMNS} FROM work_shifts ws JOIN workplaces w ON w.id = ws.workplace_id
                WHERE w.user_id = %s AND ws.id = %s
                """,
                (user_id, shift_id),
            )
            row = cur.fetchone()
        return _to_shift(row) if row else None

    def update(
        self, user_id: int, shift_id: int, workplace_name: str, work_date: date, start_time: time, end_time: time
    ) -> WorkShift | None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT ws.id FROM work_shifts ws JOIN workplaces w ON w.id = ws.workplace_id
                WHERE ws.id = %s AND w.user_id = %s
                """,
                (shift_id, user_id),
            )
            if cur.fetchone() is None:
                return None
            workplace_id = self._workplace_id(cur, user_id, workplace_name)
            cur.execute(
                """
                UPDATE work_shifts SET workplace_id = %s, work_date = %s, start_time = %s, end_time = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (workplace_id, work_date, start_time, end_time, shift_id),
            )
        return self.get(user_id, shift_id)

    def list_for_user(self, user_id: int) -> list[WorkShift]:
        with self._db.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SHIFT_COLUMNS} FROM work_shifts ws JOIN workplaces w ON w.id = ws.workplace_id
                WHERE w.user_id = %s
                ORDER BY ws.work_date, ws.start_time
                """,
                (user_id,),
            )
            return [_to_shift(r) for r in cur.fetchall()]

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
