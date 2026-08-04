from datetime import datetime
from uuid import UUID

from supabase import Client

from domain.entities.group import Group
from domain.ports.group_repository import GroupRepository

from .client import get_supabase_client

_TABLE = "groups"


def _row_to_group(row: dict) -> Group:
    return Group(
        id=UUID(row["id"]),
        name=row["name"],
        parent_id=UUID(row["parent_id"]) if row.get("parent_id") else None,
        drive_folder_id=row.get("drive_folder_id"),
        created_at=datetime.fromisoformat(row["created_at"]),
        children=[],
    )


class SupabaseGroupRepository(GroupRepository):

    def __init__(self, client: Client | None = None) -> None:
        self._db = client or get_supabase_client()

    def get_by_id(self, group_id: UUID) -> Group | None:
        response = (
            self._db.table(_TABLE)
            .select("*")
            .eq("id", str(group_id))
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return _row_to_group(response.data[0])

    def list_roots(self) -> list[Group]:
        response = (
            self._db.table(_TABLE)
            .select("*")
            .is_("parent_id", "null")
            .order("name")
            .execute()
        )
        return [_row_to_group(row) for row in (response.data or [])]

    def list_children(self, parent_id: UUID) -> list[Group]:
        response = (
            self._db.table(_TABLE)
            .select("*")
            .eq("parent_id", str(parent_id))
            .order("name")
            .execute()
        )
        return [_row_to_group(row) for row in (response.data or [])]

    def list_all(self) -> list[Group]:
        """Carga todos los grupos y construye el árbol en memoria."""
        response = (
            self._db.table(_TABLE)
            .select("*")
            .order("name")
            .execute()
        )
        all_rows = response.data or []
        all_groups: dict[UUID, Group] = {
            UUID(row["id"]): _row_to_group(row) for row in all_rows
        }

        roots: list[Group] = []
        for group in all_groups.values():
            if group.parent_id is None:
                roots.append(group)
            else:
                parent = all_groups.get(group.parent_id)
                if parent is not None:
                    parent.children.append(group)

        # Ordena children de cada raíz por nombre
        for root in roots:
            root.children.sort(key=lambda g: g.name)

        roots.sort(key=lambda g: g.name)
        return roots

    def get_by_name_and_parent(self, name: str, parent_id: UUID | None) -> Group | None:
        query = self._db.table(_TABLE).select("*").eq("name", name)
        if parent_id is None:
            query = query.is_("parent_id", "null")
        else:
            query = query.eq("parent_id", str(parent_id))
        response = query.limit(1).execute()
        if not response.data:
            return None
        return _row_to_group(response.data[0])

    def save(self, group: Group) -> None:
        payload = {
            "id": str(group.id),
            "name": group.name,
            "parent_id": str(group.parent_id) if group.parent_id else None,
            "drive_folder_id": group.drive_folder_id,
            "created_at": group.created_at.isoformat(),
        }
        self._db.table(_TABLE).insert(payload).execute()

    def update(self, group: Group) -> None:
        payload = {
            "name": group.name,
            "drive_folder_id": group.drive_folder_id,
        }
        self._db.table(_TABLE).update(payload).eq("id", str(group.id)).execute()

    def delete(self, group_id: UUID) -> None:
        self._db.table(_TABLE).delete().eq("id", str(group_id)).execute()
