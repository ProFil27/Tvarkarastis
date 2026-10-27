from app.domain.entities import PdfDocument, PdfStatus
from app.infrastructure.database import Database


class PostgresPdfDocumentRepository:
    def __init__(self, database: Database):
        self._db = database

    def add(self, user_id: int, filename: str) -> PdfDocument:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                "INSERT INTO pdf_documents (user_id, filename, status) VALUES (%s, %s, %s) RETURNING id",
                (user_id, filename, PdfStatus.UPLOADED.value),
            )
            document_id = cur.fetchone()["id"]
        return PdfDocument(document_id, user_id, filename, PdfStatus.UPLOADED)

    def set_status(self, pdf_document_id: int, status: PdfStatus) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute("UPDATE pdf_documents SET status = %s WHERE id = %s", (status.value, pdf_document_id))
