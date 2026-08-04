from uuid import UUID

from domain.exceptions import DocumentNotFoundError
from domain.ports.document_repository import DocumentRepository
from domain.ports.file_storage import FileStorage


class DeleteDocument:

    def __init__(
        self,
        document_repo: DocumentRepository,
        file_storage: FileStorage,
    ) -> None:
        self._document_repo = document_repo
        self._file_storage = file_storage

    def execute(self, employee_id: UUID, document_type_id: UUID) -> None:
        document = self._document_repo.get_by_employee_and_type(
            employee_id, document_type_id
        )
        if document is None:
            raise DocumentNotFoundError(employee_id, document_type_id)

        self._file_storage.delete(document.drive_file_id)
        self._document_repo.delete(employee_id, document_type_id)
