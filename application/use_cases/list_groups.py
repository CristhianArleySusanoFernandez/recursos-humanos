from domain.entities.group import Group
from domain.ports.group_repository import GroupRepository

from perf_debug import timed  # [PERF-DEBUG] instrumentación temporal


class ListGroups:

    def __init__(self, group_repo: GroupRepository) -> None:
        self._group_repo = group_repo

    def execute(self) -> list[Group]:
        """Retorna todos los grupos nivel 1 con sus children poblados."""
        # [PERF-DEBUG] una sola query; no debería tocar Drive.
        with timed("ListGroups: query grupos (list_all)"):
            return self._group_repo.list_all()
