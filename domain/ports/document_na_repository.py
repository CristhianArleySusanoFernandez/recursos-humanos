from abc import ABC, abstractmethod
from uuid import UUID


class DocumentNaRepository(ABC):

    @abstractmethod
    def get_na_type_ids(self, employee_id: UUID) -> set[UUID]:
        """IDs de tipos marcados como N/A para el empleado dado."""
        ...

    @abstractmethod
    def mark_na(self, employee_id: UUID, document_type_id: UUID) -> None:
        ...

    @abstractmethod
    def unmark_na(self, employee_id: UUID, document_type_id: UUID) -> None:
        ...
