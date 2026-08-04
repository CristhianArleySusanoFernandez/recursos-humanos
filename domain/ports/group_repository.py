from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from domain.entities.group import Group


class GroupRepository(ABC):

    @abstractmethod
    def get_by_id(self, group_id: UUID) -> Group | None: ...

    @abstractmethod
    def list_roots(self) -> list[Group]:
        """Retorna solo los grupos de nivel 1 (sin parent)."""
        ...

    @abstractmethod
    def list_children(self, parent_id: UUID) -> list[Group]:
        """Retorna los subgrupos directos de un grupo dado."""
        ...

    @abstractmethod
    def list_all(self) -> list[Group]:
        """Retorna todos los grupos con su lista children poblada."""
        ...

    @abstractmethod
    def get_by_name_and_parent(self, name: str, parent_id: UUID | None) -> Group | None:
        """Busca un grupo por nombre dentro de un padre dado (None = grupo raíz)."""
        ...

    @abstractmethod
    def save(self, group: Group) -> None: ...

    @abstractmethod
    def update(self, group: Group) -> None: ...

    @abstractmethod
    def delete(self, group_id: UUID) -> None: ...
