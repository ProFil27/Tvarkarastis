from datetime import date, time

from app.domain.entities import ShiftSeries, WorkShift
from app.infrastructure.database import Database
from app.infrastructure.persistence.work_shift_repository import SHIFT_COLUMNS, to_shift, workplace_id

_SERIES_COLUMNS = (
    "s.id, s.start_time, s.end_time, s.first_date, s.last_date, s.updated_at, w.name AS workplace_name"
)


def _to_series(r) -> ShiftSeries:
    return ShiftSeries(
        r["id"], r["workplace_name"], r["start_time"], r["end_time"], r["first_date"], r["last_date"], r["updated_at"]
    )


class PostgresShiftSeriesRepository:
    def __init__(self, database: Database):
        self._db = database

    def create(
        self, user_id: int, workplace_name: str, start_time: time, end_time: time, dates: list[date]
    ) -> list[WorkShift]:
        with self._db.cursor(commit=True) as cur:
            place = workplace_id(cur, user_id, workplace_name)
            cur.execute(
                """
                INSERT INTO shift_series (user_id, workplace_id, start_time, end_time, first_date, last_date)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (user_id, place, start_time, end_time, min(dates), max(dates)),
            )
            series_id = cur.fetchone()["id"]
            self._insert_shifts(cur, series_id, place, start_time, end_time, dates)
            cur.execute(
                f"""
                SELECT {SHIFT_COLUMNS} FROM work_shifts ws JOIN workplaces w ON w.id = ws.workplace_id
                WHERE ws.series_id = %s ORDER BY ws.work_date
                """,
                (series_id,),
            )
            return [to_shift(r) for r in cur.fetchall()]

    def get(self, user_id: int, series_id: int) -> ShiftSeries | None:
        with self._db.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SERIES_COLUMNS} FROM shift_series s JOIN workplaces w ON w.id = s.workplace_id
                WHERE s.id = %s AND s.user_id = %s
                """,
                (series_id, user_id),
            )
            row = cur.fetchone()
        return _to_series(row) if row else None

    def list_for_user(self, user_id: int) -> list[ShiftSeries]:
        with self._db.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SERIES_COLUMNS} FROM shift_series s JOIN workplaces w ON w.id = s.workplace_id
                WHERE s.user_id = %s ORDER BY s.first_date, s.id
                """,
                (user_id,),
            )
            return [_to_series(r) for r in cur.fetchall()]

    def update(
        self,
        user_id: int,
        series_id: int,
        workplace_name: str,
        start_time: time,
        end_time: time,
        last_date: date,
        new_dates: list[date],
    ) -> ShiftSeries | None:
        with self._db.cursor(commit=True) as cur:
            cur.execute("SELECT id FROM shift_series WHERE id = %s AND user_id = %s", (series_id, user_id))
            if cur.fetchone() is None:
                return None
            place = workplace_id(cur, user_id, workplace_name)
            cur.execute(
                """
                UPDATE shift_series SET workplace_id = %s, start_time = %s, end_time = %s, last_date = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (place, start_time, end_time, last_date, series_id),
            )
            cur.execute(
                """
                UPDATE work_shifts SET workplace_id = %s, start_time = %s, end_time = %s, updated_at = now()
                WHERE series_id = %s AND NOT is_exception
                """,
                (place, start_time, end_time, series_id),
            )
            cur.execute("DELETE FROM work_shifts WHERE series_id = %s AND work_date > %s", (series_id, last_date))
            self._insert_shifts(cur, series_id, place, start_time, end_time, new_dates)
        return self.get(user_id, series_id)

    def remove(self, user_id: int, series_id: int) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute("DELETE FROM shift_series WHERE id = %s AND user_id = %s", (series_id, user_id))
            return cur.rowcount > 0  # its shifts are removed with it (ON DELETE CASCADE)

    @staticmethod
    def _insert_shifts(cur, series_id: int, place: int, start_time: time, end_time: time, dates: list[date]) -> None:
        for day in dates:
            cur.execute(
                """
                INSERT INTO work_shifts (workplace_id, work_date, start_time, end_time, series_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (place, day, start_time, end_time, series_id),
            )
