from app.domain.entities import PdfDocument, PdfStatus
from app.infrastructure.database import Database


class PostgresPdfDocumentRepository:
    def __init__(self, database: Database):
        self._db = database

    def add(self, user_id: int, filename: str, replace_existing: bool = False) -> PdfDocument:
        with self._db.cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO pdf_documents (user_id, filename, status, replace_existing)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (user_id, filename, PdfStatus.UPLOADED.value, replace_existing),
            )
            document_id = cur.fetchone()["id"]
        return PdfDocument(document_id, user_id, filename, PdfStatus.UPLOADED, replace_existing)

    def get(self, pdf_document_id: int) -> PdfDocument | None:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, filename, status, replace_existing FROM pdf_documents WHERE id = %s",
                (pdf_document_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return PdfDocument(row["id"], row["user_id"], row["filename"], PdfStatus(row["status"]), row["replace_existing"])

    def set_status(self, pdf_document_id: int, status: PdfStatus) -> None:
        with self._db.cursor(commit=True) as cur:
            cur.execute("UPDATE pdf_documents SET status = %s WHERE id = %s", (status.value, pdf_document_id))
