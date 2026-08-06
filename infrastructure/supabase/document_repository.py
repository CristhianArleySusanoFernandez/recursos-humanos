from datetime import datetime
from uuid import UUID

from supabase import Client

from domain.entities.document import Document
from domain.ports.document_repository import DocumentRepository

from .client import get_supabase_client

_TABLE = "documents"


def _row_to_document(row: dict) -> Document:
    return Document(
        id=UUID(row["id"]),
        employee_id=UUID(row["employee_id"]),
        document_type_id=UUID(row["document_type_id"]),
        file_name=row["file_name"],
        drive_file_id=row["drive_file_id"],
        drive_url=row["drive_url"],
        uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
    )


class SupabaseDocumentRepository(DocumentRepository):

    def __init__(self, client: Client | None = None) -> None:
        self._db = client or get_supabase_client()

    def get_by_id(self, document_id: UUID) -> Document | None:
        response = (
            self._db.table(_TABLE)
            .select("*")
            .eq("id", str(document_id))
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return _row_to_document(response.data[0])

    def get_by_employee(self, employee_id: UUID) -> list[Document]:
        response = (
            self._db.table(_TABLE)
            .select("*")
            .eq("employee_id", str(employee_id))
            .order("uploaded_at", desc=True)
            .execute()
        )
        return [_row_to_document(row) for row in (response.data or [])]

    def get_by_employees(
        self, employee_ids: list[UUID]
    ) -> dict[UUID, list[Document]]:
        # Trae los documentos de todos los empleados de la lista con UNA consulta
        # bulk (filtro IN sobre employee_id), agrupados por employee_id. Se pagina
        # con .range() igual que list_all(), porque PostgREST corta a ~1000 filas
        # y varios empleados juntos superan ese tope fácilmente.
        result: dict[UUID, list[Document]] = {eid: [] for eid in employee_ids}
        if not employee_ids:
            return result

        id_strings = [str(eid) for eid in employee_ids]
        page_size = 1000
        offset = 0
        while True:
            response = (
                self._db.table(_TABLE)
                .select("*")
                .in_("employee_id", id_strings)
                .order("uploaded_at", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = response.data or []
            for row in batch:
                doc = _row_to_document(row)
                result.setdefault(doc.employee_id, []).append(doc)
            if len(batch) < page_size:
                break
            offset += page_size
        return result

    def get_by_employee_and_type(
        self, employee_id: UUID, document_type_id: UUID
    ) -> Document | None:
        response = (
            self._db.table(_TABLE)
            .select("*")
            .eq("employee_id", str(employee_id))
            .eq("document_type_id", str(document_type_id))
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return _row_to_document(response.data[0])

    def list_all(self) -> list[Document]:
        # PostgREST devuelve como máximo ~1000 filas por respuesta. La tabla de
        # documentos supera ese tope (miles de filas), así que paginamos con
        # .range() hasta agotar los resultados; de lo contrario la cola de
        # revisión quedaría truncada a las 1000 más recientes y zonas enteras
        # (p. ej. Barbosa) no aparecerían nunca.
        page_size = 1000
        offset = 0
        rows: list[dict] = []
        while True:
            response = (
                self._db.table(_TABLE)
                .select("*")
                .order("uploaded_at", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            batch = response.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return [_row_to_document(row) for row in rows]

    def save(self, document: Document) -> None:
        payload = {
            "id": str(document.id),
            "employee_id": str(document.employee_id),
            "document_type_id": str(document.document_type_id),
            "file_name": document.file_name,
            "drive_file_id": document.drive_file_id,
            "drive_url": document.drive_url,
            "uploaded_at": document.uploaded_at.isoformat(),
        }
        self._db.table(_TABLE).insert(payload).execute()

    def update(self, document: Document) -> None:
        payload = {
            "employee_id": str(document.employee_id),
            "document_type_id": str(document.document_type_id),
            "file_name": document.file_name,
            "drive_file_id": document.drive_file_id,
            "drive_url": document.drive_url,
        }
        self._db.table(_TABLE).update(payload).eq("id", str(document.id)).execute()

    def delete(self, employee_id: UUID, document_type_id: UUID) -> None:
        (
            self._db.table(_TABLE)
            .delete()
            .eq("employee_id", str(employee_id))
            .eq("document_type_id", str(document_type_id))
            .execute()
        )
