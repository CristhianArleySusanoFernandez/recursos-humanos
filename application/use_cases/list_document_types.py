from domain.entities.document_type import DocumentType
from domain.ports.document_type_repository import DocumentTypeRepository

from perf_debug import timed  # [PERF-DEBUG] instrumentación temporal


class ListDocumentTypes:

    def __init__(self, document_type_repo: DocumentTypeRepository) -> None:
        self._document_type_repo = document_type_repo

    def execute(self) -> list[DocumentType]:
        """Retorna todos los tipos de documento ordenados por categoría y order_index."""
        # [PERF-DEBUG] query + ordenamiento en Python.
        with timed("ListDocumentTypes: query tipos (list_all)"):
            types = self._document_type_repo.list_all()
        with timed(f"ListDocumentTypes: sort en Python ({len(types)} tipos)"):
            return sorted(types, key=lambda dt: (dt.category, dt.order_index))
