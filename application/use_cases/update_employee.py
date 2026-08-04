from dataclasses import dataclass
from uuid import UUID

from domain.exceptions import EmployeeNotFoundError, GroupNotFoundError
from domain.ports.employee_repository import EmployeeRepository
from domain.ports.group_repository import GroupRepository


@dataclass
class UpdateEmployeeInput:
    employee_id: UUID
    name: str | None = None
    position: str | None = None
    group_id: UUID | None = None
    is_active: bool | None = None


class UpdateEmployee:

    def __init__(
        self,
        employee_repo: EmployeeRepository,
        group_repo: GroupRepository,
    ) -> None:
        self._employee_repo = employee_repo
        self._group_repo = group_repo

    def execute(self, input: UpdateEmployeeInput) -> None:
        employee = self._employee_repo.get_by_id(input.employee_id)
        if employee is None:
            raise EmployeeNotFoundError(input.employee_id)

        if input.name is not None:
            employee.name = input.name.strip()
        if input.position is not None:
            employee.position = input.position.strip()
        if input.is_active is not None:
            employee.is_active = input.is_active
        if input.group_id is not None:
            group = self._group_repo.get_by_id(input.group_id)
            if group is None:
                raise GroupNotFoundError(input.group_id)
            if group.is_root():
                raise ValueError(
                    f"El grupo '{group.name}' es de nivel 1. "
                    "Los empleados deben asignarse a un subgrupo (nivel 2)."
                )
            employee.group_id = input.group_id

        self._employee_repo.update(employee)
