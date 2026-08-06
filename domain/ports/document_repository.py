from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from domain.entities.document import Document


class DocumentRepository(ABC):

    @abstractmethod
    def get_by_id(self, document_id: UUID) -> Document | None: ...

    @abstractmethod
    def get_by_employee(self, employee_id: UUID) -> list[Document]: ...

    @abstractmethod
    def get_by_employees(
        self, employee_ids: list[UUID]
    ) -> dict[UUID, list[Document]]:
        """
        Trae los documentos de MÚLTIPLES empleados en una sola consulta bulk
        (filtro IN), agrupados por employee_id para acceso O(1). Evita el N+1
        de llamar get_by_employee() por cada empleado en un loop.
        """
        ...

    @abstractmethod
    def get_by_employee_and_type(
        self, employee_id: UUID, document_type_id: UUID
    ) -> Document | None: ...

    @abstractmethod
    def list_all(self) -> list[Document]:
        """Retorna todos los documentos existentes (para la cola de revisión)."""
        ...

    @abstractmethod
    def save(self, document: Document) -> None: ...

    @abstractmethod
    def update(self, document: Document) -> None:
        """Actualiza un documento existente identificado por su id."""
        ...

    @abstractmethod
    def delete(self, employee_id: UUID, document_type_id: UUID) -> None: ...

    @abstractmethod
    def mark_verified(self, document_id: UUID, verified: bool) -> None:
        """
        Marca o desmarca un documento como verificado manualmente. Cuando
        verified=True registra la marca de tiempo; cuando False la limpia.
        """
        ...
