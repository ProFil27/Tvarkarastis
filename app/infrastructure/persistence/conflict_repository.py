from app.domain.entities import Conflict, DetectedConflict
from app.infrastructure.database import Database


class PostgresConflictRepository:
    def __init__(self, database: Database):
        self._db = database

    def list_active(self, user_id: int) -> list[Conflict]:
        with self._db.cursor() as cur:
            cur.execute(
                """
                SELECT id, study_event_id, work_shift_id, overlap_minutes
                FROM conflicts WHERE user_id = %s AND status = 'AKTYVUS'
                """,
                (user_id,),
            )
            return [Conflict(**row) for row in cur.fetchall()]

    def replace_active(self, user_id: int, detected: list[DetectedConflict]) -> list[Conflict]:
        """Keep existing pairs, delete stale ones, insert new ones; return the new ones."""
        created: list[Conflict] = []
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "SELECT id, study_event_id, work_shift_id FROM conflicts WHERE user_id = %s AND status = 'AKTYVUS'",
                (user_id,),
            )
            existing = {(r["study_event_id"], r["work_shift_id"]): r["id"] for r in cur.fetchall()}
            detected_keys = {(d.study_event_id, d.work_shift_id) for d in detected}

            for key, conflict_id in existing.items():
                if key not in detected_keys:
                    cur.execute("DELETE FROM conflicts WHERE id = %s", (conflict_id,))

            for item in detected:
                key = (item.study_event_id, item.work_shift_id)
                if key in existing:
                    cur.execute(
                        "UPDATE conflicts SET overlap_minutes = %s WHERE id = %s",
                        (item.overlap_minutes, existing[key]),
                    )
                    continue
                cur.execute(
                    """
                    INSERT INTO conflicts (user_id, study_event_id, work_shift_id, overlap_minutes)
                    VALUES (%s, %s, %s, %s) RETURNING id
                    """,
                    (user_id, item.study_event_id, item.work_shift_id, item.overlap_minutes),
                )
                created.append(
                    Conflict(cur.fetchone()["id"], item.study_event_id, item.work_shift_id, item.overlap_minutes)
                )
        return created
