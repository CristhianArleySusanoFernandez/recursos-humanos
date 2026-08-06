from uuid import UUID

from domain.entities.employee import Employee
from domain.ports.document_repository import DocumentRepository
from domain.ports.employee_repository import EmployeeRepository

from perf_debug import log, timed  # [PERF-DEBUG] instrumentación temporal


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
        # [PERF-DEBUG] tiempo de la query que trae los empleados.
        with timed(f"ListEmployees: query empleados (group_id={group_id}, active={active_only})"):
            if group_id is not None:
                employees = self._employee_repo.list_by_group(group_id, active_only)
            else:
                employees = self._employee_repo.list_all(active_only)

        # [PERF-DEBUG] El siguiente loop hace UNA query a Supabase por CADA empleado
        # (N+1). Medimos el total y el número de queries para confirmarlo.
        with timed(f"ListEmployees: N+1 documentos ({len(employees)} queries get_by_employee)"):
            for employee in employees:
                employee.documents = self._document_repo.get_by_employee(employee.id)
        log(f"ListEmployees: {len(employees)} empleados → {len(employees)} queries de documentos")

        return employees
