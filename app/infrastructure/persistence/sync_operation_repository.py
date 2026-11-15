from datetime import datetime

from app.domain.entities import SyncOperation, SyncOperationType, SyncStatus
from app.infrastructure.database import Database

_COLUMNS = """id, user_id, operation_type, status, started_at, finished_at, created_count, updated_count,
              deleted_count, error_code, error_message"""


def _to_operation(row) -> SyncOperation:
    return SyncOperation(
        id=row["id"],
        user_id=row["user_id"],
        operation_type=SyncOperationType(row["operation_type"]),
        status=SyncStatus(row["status"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        created_count=row["created_count"],
        updated_count=row["updated_count"],
        deleted_count=row["deleted_count"],
        error_code=row["error_code"],
        error_message=row["error_message"],
    )


class PostgresSyncOperationRepository:
    def __init__(self, database: Database):
        self._db = database

    def start(self, user_id: int, operation_type: SyncOperationType, started_at: datetime) -> int:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO sync_operations (user_id, operation_type, status, started_at) VALUES (%s, %s, %s, %s) RETURNING id",
                (user_id, operation_type.value, SyncStatus.IN_PROGRESS.value, started_at),
            )
            return cur.fetchone()["id"]

    def finish(
        self,
        operation_id: int,
        status: SyncStatus,
        finished_at: datetime,
        created: int,
        updated: int,
        deleted: int,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE sync_operations SET status = %s, finished_at = %s, created_count = %s, updated_count = %s,
                    deleted_count = %s, error_code = %s, error_message = %s
                WHERE id = %s
                """,
                (status.value, finished_at, created, updated, deleted, error_code, error_message, operation_id),
            )

    def last(self, user_id: int) -> SyncOperation | None:
        return self._latest(user_id, "status <> 'VYKDOMAS'")

    def last_success(self, user_id: int) -> SyncOperation | None:
        return self._latest(user_id, "status = 'SEKMINGAS'")

    def has_export(self, user_id: int) -> bool:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM sync_operations WHERE user_id = %s AND operation_type = %s AND status = %s) AS found",
                (user_id, SyncOperationType.EXPORT.value, SyncStatus.SUCCESS.value),
            )
            return cur.fetchone()["found"]

    def _latest(self, user_id: int, condition: str) -> SyncOperation | None:
        with self._db.cursor() as cur:
            cur.execute(
                f"SELECT {_COLUMNS} FROM sync_operations WHERE user_id = %s AND {condition} "
                "ORDER BY finished_at DESC NULLS LAST, id DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
        return _to_operation(row) if row else None
