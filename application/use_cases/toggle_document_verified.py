from dataclasses import dataclass
from uuid import UUID

from domain.ports.document_repository import DocumentRepository


@dataclass
class ToggleDocumentVerifiedInput:
    document_id: UUID
    verified: bool


class ToggleDocumentVerified:
    """
    Marca o desmarca un documento como verificado manualmente.
    Independiente de N/A y del tipo; no afecta la completitud.
    """

    def __init__(self, document_repo: DocumentRepository) -> None:
        self._document_repo = document_repo

    def execute(self, data: ToggleDocumentVerifiedInput) -> None:
        self._document_repo.mark_verified(data.document_id, data.verified)
