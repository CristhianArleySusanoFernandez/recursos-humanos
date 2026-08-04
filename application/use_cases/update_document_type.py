from dataclasses import dataclass
from uuid import UUID

from domain.exceptions import DocumentTypeNotFoundError
from domain.ports.document_type_repository import DocumentTypeRepository


@dataclass
class UpdateDocumentTypeInput:
    document_type_id: UUID
    name: str | None = None
    is_active: bool | None = None
    order_index: int | None = None


class UpdateDocumentType:

    def __init__(self, document_type_repo: DocumentTypeRepository) -> None:
        self._document_type_repo = document_type_repo

    def execute(self, input: UpdateDocumentTypeInput) -> None:
        doc_type = self._document_type_repo.get_by_id(input.document_type_id)
        if doc_type is None:
            raise DocumentTypeNotFoundError(str(input.document_type_id))

        if input.name is not None:
            doc_type.name = input.name.strip()
        if input.is_active is not None:
            doc_type.is_active = input.is_active
        if input.order_index is not None:
            doc_type.order_index = input.order_index

        self._document_type_repo.update(doc_type)
