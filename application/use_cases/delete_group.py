from uuid import UUID

from domain.exceptions import (
    GroupHasChildrenError,
    GroupHasEmployeesError,
    GroupNotFoundError,
)
from domain.ports.employee_repository import EmployeeRepository
from domain.ports.group_repository import GroupRepository


class DeleteGroup:

    def __init__(
        self,
        group_repo: GroupRepository,
        employee_repo: EmployeeRepository,
    ) -> None:
        self._group_repo = group_repo
        self._employee_repo = employee_repo

    def execute(self, group_id: UUID) -> None:
        group = self._group_repo.get_by_id(group_id)
        if group is None:
            raise GroupNotFoundError(group_id)

        children = self._group_repo.list_children(group_id)
        if children:
            raise GroupHasChildrenError(group.name)

        active = self._employee_repo.list_by_group(group_id, active_only=True)
        if active:
            raise GroupHasEmployeesError(
                f"El grupo '{group.name}' tiene empleados activos. Desactívalos primero."
            )

        # Si hay inactivos, desvincula su group_id antes de borrar el grupo
        inactive = self._employee_repo.list_by_group(group_id, active_only=False)
        if inactive:
            self._employee_repo.bulk_clear_group(group_id)

        self._group_repo.delete(group_id)
