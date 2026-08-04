from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from domain.entities.document_type import DocumentType


class DocumentTypeRepository(ABC):

    @abstractmethod
    def list_active(self, exclude_category: str | None = None) -> list[DocumentType]:
        """
        Tipos activos. Si exclude_category se especifica, omite los de esa
        categoría (se usa con "EXTRA" para dejar fuera los tipos generados
        automáticamente por la subida masiva).
        """

    @abstractmethod
    def list_all(self) -> list[DocumentType]: ...

    @abstractmethod
    def get_by_id(self, document_type_id: UUID) -> DocumentType | None: ...

    @abstractmethod
    def get_by_code(self, code: str) -> DocumentType | None: ...

    @abstractmethod
    def save(self, document_type: DocumentType) -> None: ...

    @abstractmethod
    def update(self, document_type: DocumentType) -> None: ...
