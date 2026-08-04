from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from .document import Document
from .document_type import EXTRA_CATEGORY, DocumentType


@dataclass
class Employee:
    id: UUID
    name: str
    position: str
    group_id: UUID | None
    is_active: bool
    created_at: datetime
    documents: list[Document] = field(default_factory=list)

    @classmethod
    def create(cls, name: str, position: str, group_id: UUID | None = None) -> Employee:
        return cls(
            id=uuid4(),
            name=name.strip(),
            position=position.strip(),
            group_id=group_id,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    def add_document(self, document: Document) -> None:
        """Agrega el documento; si ya existe uno del mismo tipo lo reemplaza."""
        self.documents = [
            d for d in self.documents if d.document_type_id != document.document_type_id
        ]
        self.documents.append(document)

    def remove_document(self, document_type_id: UUID) -> None:
        self.documents = [
            d for d in self.documents if d.document_type_id != document_type_id
        ]

    def get_documents_by_category(
        self,
        category: str,
        document_types: list[DocumentType],
    ) -> list[tuple[DocumentType, Document | None]]:
        """
        Retorna todos los tipos activos de la categoría dada, junto con el
        documento del empleado si existe, o None si falta.
        Ordenado por order_index.
        """
        by_type_id: dict[UUID, Document] = {d.document_type_id: d for d in self.documents}
        types_in_category = sorted(
            (dt for dt in document_types if dt.category == category and dt.is_active),
            key=lambda dt: dt.order_index,
        )
        return [(dt, by_type_id.get(dt.id)) for dt in types_in_category]

    def completion_ratio(self, document_types: list[DocumentType]) -> tuple[int, int]:
        """
        Retorna (documentos presentes, total de tipos requeridos).

        Los tipos de categoría EXTRA se excluyen de ambos términos: son
        archivos adicionales generados por la subida masiva, no documentos
        exigidos, y no deben afectar la completitud.
        """
        required_ids = {
            dt.id for dt in document_types
            if dt.is_active and dt.category != EXTRA_CATEGORY
        }
        present = sum(1 for d in self.documents if d.document_type_id in required_ids)
        return present, len(required_ids)

    def get_extra_documents(
        self,
        document_types: list[DocumentType],
    ) -> list[tuple[DocumentType, Document]]:
        """Documentos que el empleado tiene bajo un tipo de categoría EXTRA."""
        extra_types = {
            dt.id: dt for dt in document_types if dt.category == EXTRA_CATEGORY
        }
        pairs = [
            (extra_types[d.document_type_id], d)
            for d in self.documents
            if d.document_type_id in extra_types
        ]
        return sorted(pairs, key=lambda pair: pair[0].name.lower())

    def deactivate(self) -> None:
        self.is_active = False

    def reactivate(self) -> None:
        self.is_active = True
