from app.domain.entities import AiRequestType
from app.infrastructure.database import Database


class PostgresAiRequestLog:
    def __init__(self, database: Database):
        self._db = database

    def start(self, user_id: int, request_type: AiRequestType, pdf_document_id: int | None = None) -> int:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO ai_requests (user_id, pdf_document_id, request_type, attempt_count)
                VALUES (%s, %s, %s, 0) RETURNING id
                """,
                (user_id, pdf_document_id, request_type.value),
            )
            return cur.fetchone()["id"]

    def finish(self, ai_request_id: int, attempts: int, error: str | None) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "UPDATE ai_requests SET finished_at = now(), attempt_count = %s, error_message = %s WHERE id = %s",
                (attempts, error, ai_request_id),
            )
