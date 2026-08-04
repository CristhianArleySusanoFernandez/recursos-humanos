from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class Group:
    id: UUID
    name: str
    parent_id: UUID | None      # None = grupo de nivel 1 (raíz)
    drive_folder_id: str | None
    created_at: datetime
    children: list[Group] = field(default_factory=list)

    def is_root(self) -> bool:
        return self.parent_id is None
