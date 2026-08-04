from dataclasses import dataclass
from uuid import UUID

from domain.exceptions import GroupNotFoundError
from domain.ports.group_repository import GroupRepository


@dataclass
class UpdateGroupInput:
    group_id: UUID
    name: str


class UpdateGroup:

    def __init__(self, group_repo: GroupRepository) -> None:
        self._group_repo = group_repo

    def execute(self, input: UpdateGroupInput) -> None:
        group = self._group_repo.get_by_id(input.group_id)
        if group is None:
            raise GroupNotFoundError(input.group_id)

        group.name = input.name.strip()
        self._group_repo.update(group)
