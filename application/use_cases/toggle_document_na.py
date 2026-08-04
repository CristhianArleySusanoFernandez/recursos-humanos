from dataclasses import dataclass
from uuid import UUID

from domain.ports.document_na_repository import DocumentNaRepository


@dataclass
class ToggleDocumentNaInput:
    employee_id: UUID
    document_type_id: UUID


class ToggleDocumentNa:

    def __init__(self, document_na_repo: DocumentNaRepository) -> None:
        self._repo = document_na_repo

    def execute(self, input: ToggleDocumentNaInput) -> bool:
        """Alterna N/A. Retorna True si quedó marcado como N/A."""
        na_ids = self._repo.get_na_type_ids(input.employee_id)
        if input.document_type_id in na_ids:
            self._repo.unmark_na(input.employee_id, input.document_type_id)
            return False
        self._repo.mark_na(input.employee_id, input.document_type_id)
        return True
