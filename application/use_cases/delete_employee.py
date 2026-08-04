from uuid import UUID

from domain.exceptions import EmployeeIsActiveError, EmployeeNotFoundError
from domain.ports.document_repository import DocumentRepository
from domain.ports.employee_repository import EmployeeRepository
from domain.ports.file_storage import FileStorage


class DeleteEmployee:

    def __init__(
        self,
        employee_repo: EmployeeRepository,
        document_repo: DocumentRepository,
        file_storage: FileStorage,
    ) -> None:
        self._employee_repo = employee_repo
        self._document_repo = document_repo
        self._file_storage = file_storage

    def execute(self, employee_id: UUID) -> None:
        employee = self._employee_repo.get_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundError(employee_id)
        if employee.is_active:
            raise EmployeeIsActiveError(employee.name)

        documents = self._document_repo.get_by_employee(employee_id)

        for doc in documents:
            try:
                self._file_storage.delete(doc.drive_file_id)
            except Exception:
                pass
            self._document_repo.delete(employee_id, doc.document_type_id)

        self._employee_repo.delete(employee_id)
