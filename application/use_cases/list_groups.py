from domain.entities.group import Group
from domain.ports.group_repository import GroupRepository


class ListGroups:

    def __init__(self, group_repo: GroupRepository) -> None:
        self._group_repo = group_repo

    def execute(self) -> list[Group]:
        """Retorna todos los grupos nivel 1 con sus children poblados."""
        return self._group_repo.list_all()
