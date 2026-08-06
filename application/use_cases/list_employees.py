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

        # UNA sola consulta bulk trae los documentos de TODOS los empleados a la
        # vez (filtro IN + paginación), en lugar del antiguo N+1 (una query por
        # empleado). Luego se asignan desde el diccionario en memoria, sin más red.
        with timed(f"ListEmployees: documentos bulk (1 query get_by_employees, {len(employees)} empleados)"):
            docs_by_employee = self._document_repo.get_by_employees(
                [employee.id for employee in employees]
            )
        for employee in employees:
            employee.documents = docs_by_employee.get(employee.id, [])
        log(f"ListEmployees: {len(employees)} empleados → 1 query bulk de documentos")

        return employees
