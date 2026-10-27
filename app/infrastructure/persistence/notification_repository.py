from app.domain.entities import Notification
from app.infrastructure.database import Database


class PostgresNotificationRepository:
    def __init__(self, database: Database):
        self._db = database

    def add(self, user_id: int, conflict_id: int | None, message: str) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO notifications (user_id, conflict_id, message) VALUES (%s, %s, %s)",
                (user_id, conflict_id, message),
            )

    def list_unread(self, user_id: int) -> list[Notification]:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT id, message FROM notifications WHERE user_id = %s AND is_read = FALSE ORDER BY created_at DESC",
                (user_id,),
            )
            return [Notification(**row) for row in cur.fetchall()]

    def mark_read(self, user_id: int, notification_id: int) -> bool:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s",
                (notification_id, user_id),
            )
            return cur.rowcount > 0
