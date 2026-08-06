from datetime import datetime
from uuid import UUID

from supabase import Client

from domain.entities.employee import Employee
from domain.ports.employee_repository import EmployeeRepository

from .client import get_supabase_client

_TABLE = "employees"


def _row_to_employee(row: dict) -> Employee:
    return Employee(
        id=UUID(row["id"]),
        name=row["name"],
        position=row["position"],
        group_id=UUID(row["group_id"]) if row.get("group_id") else None,
        is_active=row["is_active"],
        created_at=datetime.fromisoformat(row["created_at"]),
        documents=[],
    )


class SupabaseEmployeeRepository(EmployeeRepository):

    def __init__(self, client: Client | None = None) -> None:
        self._db = client or get_supabase_client()

    def get_by_id(self, employee_id: UUID) -> Employee | None:
        response = (
            self._db.table(_TABLE)
            .select("*")
            .eq("id", str(employee_id))
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return _row_to_employee(response.data[0])

    def list_by_group(self, group_id: UUID, active_only: bool = True) -> list[Employee]:
        query = (
            self._db.table(_TABLE).select("*")
            .eq("group_id", str(group_id))
            .eq("is_active", active_only)  # True = activos, False = inactivos
        )
        response = query.order("name").execute()
        return [_row_to_employee(row) for row in (response.data or [])]

    def search_by_name(self, query: str, limit: int = 15) -> list[Employee]:
        """
        Busca empleados por nombre (ILIKE, insensible a mayúsculas) entre TODOS
        (activos e inactivos). Devuelve como máximo `limit` resultados.
        """
        term = (query or "").strip()
        if not term:
            return []
        response = (
            self._db.table(_TABLE)
            .select("*")
            .ilike("name", f"%{term}%")
            .order("name")
            .limit(limit)
            .execute()
        )
        return [_row_to_employee(row) for row in (response.data or [])]

    def list_all(self, active_only: bool = True) -> list[Employee]:
        # active_only=True  → solo activos
        # active_only=False → solo inactivos (NO "todos")
        query = self._db.table(_TABLE).select("*").eq("is_active", active_only)
        response = query.order("name").execute()
        return [_row_to_employee(row) for row in (response.data or [])]

    def save(self, employee: Employee) -> None:
        payload = {
            "id": str(employee.id),
            "name": employee.name,
            "position": employee.position,
            "group_id": str(employee.group_id) if employee.group_id else None,
            "is_active": employee.is_active,
            "created_at": employee.created_at.isoformat(),
        }
        self._db.table(_TABLE).insert(payload).execute()

    def update(self, employee: Employee) -> None:
        payload = {
            "name": employee.name,
            "position": employee.position,
            "group_id": str(employee.group_id) if employee.group_id else None,
            "is_active": employee.is_active,
        }
        self._db.table(_TABLE).update(payload).eq("id", str(employee.id)).execute()

    def delete(self, employee_id: UUID) -> None:
        self._db.table(_TABLE).delete().eq("id", str(employee_id)).execute()

    def bulk_clear_group(self, group_id: UUID) -> None:
        self._db.table(_TABLE).update({"group_id": None}).eq("group_id", str(group_id)).execute()
