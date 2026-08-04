from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from domain.entities.document_type import DocumentType
from domain.ports.document_type_repository import DocumentTypeRepository

_VALID_CATEGORIES = {"INGRESO", "RETIRO"}


@dataclass
class CreateDocumentTypeInput:
    name: str
    code: str
    category: str
    order_index: int


class CreateDocumentType:

    def __init__(self, document_type_repo: DocumentTypeRepository) -> None:
        self._document_type_repo = document_type_repo

    def execute(self, input: CreateDocumentTypeInput) -> None:
        if input.category not in _VALID_CATEGORIES:
            raise ValueError(
                f"Categoría '{input.category}' no válida. "
                f"Debe ser una de: {', '.join(sorted(_VALID_CATEGORIES))}."
            )

        document_type = DocumentType(
            id=uuid4(),
            name=input.name.strip(),
            code=input.code.strip().upper(),
            category=input.category,
            is_active=True,
            order_index=input.order_index,
            created_at=datetime.now(timezone.utc),
        )
        self._document_type_repo.save(document_type)
