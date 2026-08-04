from dataclasses import dataclass
from uuid import UUID

from domain.entities.employee import Employee
from domain.exceptions import GroupNotFoundError
from domain.ports.employee_repository import EmployeeRepository
from domain.ports.group_repository import GroupRepository


@dataclass
class CreateEmployeeInput:
    name: str
    position: str
    group_id: UUID


class CreateEmployee:

    def __init__(
        self,
        employee_repo: EmployeeRepository,
        group_repo: GroupRepository,
    ) -> None:
        self._employee_repo = employee_repo
        self._group_repo = group_repo

    def execute(self, input: CreateEmployeeInput) -> None:
        group = self._group_repo.get_by_id(input.group_id)
        if group is None:
            raise GroupNotFoundError(input.group_id)
        if group.is_root():
            raise ValueError(
                f"El grupo '{group.name}' es de nivel 1. "
                "Los empleados deben asignarse a un subgrupo (nivel 2)."
            )

        employee = Employee.create(
            name=input.name,
            position=input.position,
            group_id=input.group_id,
        )
        self._employee_repo.save(employee)
