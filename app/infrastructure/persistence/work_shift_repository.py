from datetime import date, time

from app.domain.entities import WorkShift
from app.infrastructure.database import Database

SHIFT_COLUMNS = """ws.id, ws.work_date, ws.start_time, ws.end_time, ws.updated_at, ws.series_id, ws.is_exception,
                   w.name AS workplace_name"""


def to_shift(r) -> WorkShift:
    return WorkShift(
        r["id"], r["workplace_name"], r["work_date"], r["start_time"], r["end_time"], r["updated_at"],
        r["series_id"], r["is_exception"],
    )


def workplace_id(cur, user_id: int, workplace_name: str) -> int:
    """The user's workplace with this name; created if it does not exist yet."""
    cur.execute("SELECT id FROM workplaces WHERE user_id = %s AND name = %s", (user_id, workplace_name))
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute("INSERT INTO workplaces (user_id, name) VALUES (%s, %s) RETURNING id", (user_id, workplace_name))
    return cur.fetchone()["id"]


class PostgresWorkShiftRepository:
    def __init__(self, database: Database):
        self._db = database

    def add(self, user_id: int, workplace_name: str, work_date: date, start_time: time, end_time: time) -> WorkShift:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO work_shifts (workplace_id, work_date, start_time, end_time)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (workplace_id(cur, user_id, workplace_name), work_date, start_time, end_time),
            )
            shift_id = cur.fetchone()["id"]
        return self.get(user_id, shift_id)

    def get(self, user_id: int, shift_id: int) -> WorkShift | None:
        with self._db.cursor() as cur:
            cur.execute(
                f"""
                SELECT {SHIFT_COLUMNS} FROM work_shifts ws JOIN workplaces w ON w.id = ws.workplace_id
                WHERE w.user_id = %s AND ws.id = %s
                """,
                (user_id, shift_id),
            )
            row = cur.fetchone()
        return to_shift(row) if row else None

    def update(
        self, user_id: int, shift_id: int, workplace_name: str, work_date: date, start_time: time, end_time: time
    ) -> WorkShift | None:
        """Change one shift. If it belongs to a series it becomes an exception: the series stops following it."""
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                SELECT ws.series_id FROM work_shifts ws JOIN workplaces w ON w.id = ws.workplace_id
                WHERE ws.id = %s AND w.user_id = %s
                """,
                (shift_id, user_id),
            )
            current = cur.fetchone()
            if current is None:
                return None
            cur.execute(
                """
                UPDATE work_shifts SET workplace_id = %s, work_date = %s, start_time = %s, end_time = %s,
                    is_exception = (series_id IS NOT NULL), updated_at = now()
                WHERE id = %s
                """,
                (workplace_id(cur, user_id, workplace_name), work_date, start_time, end_time, shift_id),
            )
            self._touch_series(cur, current["series_id"])
        return self.get(user_id, shift_id)

    def list_for_user(self, user_id: int) -> list[WorkShift]:
        with self._db.cursor() as cur:
            cur.execute(
                f"""
                SELECT {SHIFT_COLUMNS} FROM work_shifts ws JOIN workplaces w ON w.id = ws.workplace_id
                WHERE w.user_id = %s
                ORDER BY ws.work_date, ws.start_time
                """,
                (user_id,),
            )
            return [to_shift(r) for r in cur.fetchall()]

    def remove(self, user_id: int, shift_id: int) -> bool:
        """Remove one shift. A series loses that day; a series with no shifts left disappears."""
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                DELETE FROM work_shifts ws
                USING workplaces w
                WHERE ws.id = %s AND ws.workplace_id = w.id AND w.user_id = %s
                RETURNING ws.series_id
                """,
                (shift_id, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return False
            series_id = row["series_id"]
            if series_id is not None:
                cur.execute("SELECT count(*) AS n FROM work_shifts WHERE series_id = %s", (series_id,))
                if cur.fetchone()["n"] == 0:
                    cur.execute("DELETE FROM shift_series WHERE id = %s", (series_id,))
                else:
                    self._touch_series(cur, series_id)
            return True

    @staticmethod
    def _touch_series(cur, series_id: int | None) -> None:
        """Mark the series as changed so that the calendar sync updates its Google event."""
        if series_id is not None:
            cur.execute("UPDATE shift_series SET updated_at = now() WHERE id = %s", (series_id,))
