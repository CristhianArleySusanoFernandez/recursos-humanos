"""
Recategoriza un documento ya subido: cambia su document_type_id.

A diferencia de la subida (que crea documentos nuevos), aquí se reasigna el
tipo de un documento existente. Si el empleado ya tiene otro documento del
tipo destino, se produce un CONFLICTO porque el esquema impone
UNIQUE(employee_id, document_type_id). El conflicto se resuelve explícitamente
desde el frontend:

  - resolve_conflict=None      → no toca nada; devuelve estado "conflict" para
                                 que el frontend pregunte al usuario.
  - resolve_conflict="replace" → elimina el documento que ya ocupaba ese tipo
                                 (Drive + BD) y reasigna el actual.
  - resolve_conflict="cancel"  → no hace nada; devuelve estado "cancelled".

No toca la subida individual ni la masiva.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from domain.exceptions import DocumentTypeNotFoundError, DomainError
from domain.ports.document_repository import DocumentRepository
from domain.ports.document_type_repository import DocumentTypeRepository
from domain.ports.file_storage import FileStorage

# Estados posibles del resultado.
STATUS_UPDATED = "updated"
STATUS_CONFLICT = "conflict"
STATUS_CANCELLED = "cancelled"

# Valores válidos para resolve_conflict.
RESOLVE_REPLACE = "replace"
RESOLVE_CANCEL = "cancel"


class DocumentByIdNotFoundError(DomainError):
    def __init__(self, document_id: UUID) -> None:
        super().__init__(f"Documento con id '{document_id}' no encontrado.")
        self.document_id = document_id


@dataclass
class ReclassifyDocumentInput:
    document_id: UUID
    new_document_type_id: UUID
    resolve_conflict: str | None = None  # None | "replace" | "cancel"


@dataclass
class ReclassifyDocumentResult:
    status: str                       # STATUS_UPDATED | STATUS_CONFLICT | STATUS_CANCELLED
    existing_file_name: str | None = None      # nombre del doc en conflicto
    existing_document_type_name: str | None = None


class ReclassifyDocument:

    def __init__(
        self,
        document_repo: DocumentRepository,
        document_type_repo: DocumentTypeRepository,
        file_storage: FileStorage,
    ) -> None:
        self._document_repo = document_repo
        self._document_type_repo = document_type_repo
        self._file_storage = file_storage

    def execute(self, data: ReclassifyDocumentInput) -> ReclassifyDocumentResult:
        document = self._document_repo.get_by_id(data.document_id)
        if document is None:
            raise DocumentByIdNotFoundError(data.document_id)

        new_type = self._document_type_repo.get_by_id(data.new_document_type_id)
        if new_type is None:
            raise DocumentTypeNotFoundError(str(data.new_document_type_id))

        # Sin cambios: el documento ya es de ese tipo.
        if document.document_type_id == data.new_document_type_id:
            return ReclassifyDocumentResult(status=STATUS_UPDATED)

        # ¿El empleado ya tiene un documento del tipo destino?
        existing = self._document_repo.get_by_employee_and_type(
            document.employee_id, data.new_document_type_id
        )

        if existing is None:
            self._reassign(document, data.new_document_type_id)
            return ReclassifyDocumentResult(status=STATUS_UPDATED)

        # ── Hay conflicto ────────────────────────────────────────────────
        if data.resolve_conflict is None:
            return ReclassifyDocumentResult(
                status=STATUS_CONFLICT,
                existing_file_name=existing.file_name,
                existing_document_type_name=new_type.name,
            )

        if data.resolve_conflict == RESOLVE_CANCEL:
            return ReclassifyDocumentResult(status=STATUS_CANCELLED)

        if data.resolve_conflict == RESOLVE_REPLACE:
            # Elimina el documento que ocupaba el tipo destino (Drive + BD).
            try:
                self._file_storage.delete(existing.drive_file_id)
            except Exception:
                pass  # si falla Drive, igual liberamos el registro en BD
            self._document_repo.delete(existing.employee_id, existing.document_type_id)
            # Ahora el tipo destino está libre: reasigna el documento actual.
            self._reassign(document, data.new_document_type_id)
            return ReclassifyDocumentResult(status=STATUS_UPDATED)

        raise DomainError(
            f"resolve_conflict inválido: '{data.resolve_conflict}'. "
            f"Usa None, '{RESOLVE_REPLACE}' o '{RESOLVE_CANCEL}'."
        )

    def _reassign(self, document, new_document_type_id: UUID) -> None:
        """Reasigna el tipo del documento (Document es inmutable)."""
        updated = replace(document, document_type_id=new_document_type_id)
        self._document_repo.update(updated)
