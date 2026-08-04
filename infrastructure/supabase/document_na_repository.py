from uuid import UUID

from supabase import Client

from domain.ports.document_na_repository import DocumentNaRepository

from .client import get_supabase_client

_TABLE = "document_na"


class SupabaseDocumentNaRepository(DocumentNaRepository):

    def __init__(self, client: Client | None = None) -> None:
        self._db = client or get_supabase_client()

    def get_na_type_ids(self, employee_id: UUID) -> set[UUID]:
        response = (
            self._db.table(_TABLE)
            .select("document_type_id")
            .eq("employee_id", str(employee_id))
            .execute()
        )
        return {UUID(row["document_type_id"]) for row in (response.data or [])}

    def mark_na(self, employee_id: UUID, document_type_id: UUID) -> None:
        self._db.table(_TABLE).upsert({
            "employee_id": str(employee_id),
            "document_type_id": str(document_type_id),
        }).execute()

    def unmark_na(self, employee_id: UUID, document_type_id: UUID) -> None:
        (
            self._db.table(_TABLE)
            .delete()
            .eq("employee_id", str(employee_id))
            .eq("document_type_id", str(document_type_id))
            .execute()
        )
