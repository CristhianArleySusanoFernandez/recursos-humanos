from uuid import UUID

from domain.entities.employee import Employee
from domain.ports.document_repository import DocumentRepository
from domain.ports.employee_repository import EmployeeRepository


class ListEmployees:

    def __init__(
        self,
        employee_repo: EmployeeRepository,
        document_repo: DocumentRepository,
    ) -> None:
        self._employee_repo = employee_repo
        self._document_repo = document_repo

    def execute(
        self,
        group_id: UUID | None = None,
        active_only: bool = True,
    ) -> list[Employee]:
        if group_id is not None:
            employees = self._employee_repo.list_by_group(group_id, active_only)
        else:
            employees = self._employee_repo.list_all(active_only)

        for employee in employees:
            employee.documents = self._document_repo.get_by_employee(employee.id)

        return employees
