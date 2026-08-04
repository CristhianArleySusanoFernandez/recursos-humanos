from domain.entities.document_type import DocumentType
from domain.ports.document_type_repository import DocumentTypeRepository


class ListDocumentTypes:

    def __init__(self, document_type_repo: DocumentTypeRepository) -> None:
        self._document_type_repo = document_type_repo

    def execute(self) -> list[DocumentType]:
        """Retorna todos los tipos de documento ordenados por categoría y order_index."""
        return sorted(
            self._document_type_repo.list_all(),
            key=lambda dt: (dt.category, dt.order_index),
        )
