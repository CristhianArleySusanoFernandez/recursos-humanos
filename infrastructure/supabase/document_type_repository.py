from datetime import datetime
from uuid import UUID

from supabase import Client

from domain.entities.document_type import DocumentType
from domain.ports.document_type_repository import DocumentTypeRepository

from .client import get_supabase_client

_TABLE = "document_types"


def _row_to_document_type(row: dict) -> DocumentType:
    return DocumentType(
        id=UUID(row["id"]),
        name=row["name"],
        code=row["code"],
        category=row["category"],
        is_active=row["is_active"],
        order_index=row["order_index"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SupabaseDocumentTypeRepository(DocumentTypeRepository):

    def __init__(self, client: Client | None = None) -> None:
        self._db = client or get_supabase_client()

    def list_active(self, exclude_category: str | None = None) -> list[DocumentType]:
        query = self._db.table(_TABLE).select("*").eq("is_active", True)
        if exclude_category is not None:
            query = query.neq("category", exclude_category)
        response = query.order("category").order("order_index").execute()
        return [_row_to_document_type(row) for row in (response.data or [])]

    def list_all(self) -> list[DocumentType]:
        response = (
            self._db.table(_TABLE)
            .select("*")
            .order("category")
            .order("order_index")
            .execute()
        )
        return [_row_to_document_type(row) for row in (response.data or [])]

    def get_by_id(self, document_type_id: UUID) -> DocumentType | None:
        response = (
            self._db.table(_TABLE)
            .select("*")
            .eq("id", str(document_type_id))
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return _row_to_document_type(response.data[0])

    def get_by_code(self, code: str) -> DocumentType | None:
        response = (
            self._db.table(_TABLE)
            .select("*")
            .eq("code", code.upper())
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return _row_to_document_type(response.data[0])

    def save(self, document_type: DocumentType) -> None:
        payload = {
            "id": str(document_type.id),
            "name": document_type.name,
            "code": document_type.code,
            "category": document_type.category,
            "is_active": document_type.is_active,
            "order_index": document_type.order_index,
            "created_at": document_type.created_at.isoformat(),
        }
        self._db.table(_TABLE).insert(payload).execute()

    def update(self, document_type: DocumentType) -> None:
        payload = {
            "name": document_type.name,
            "is_active": document_type.is_active,
            "order_index": document_type.order_index,
        }
        self._db.table(_TABLE).update(payload).eq("id", str(document_type.id)).execute()
