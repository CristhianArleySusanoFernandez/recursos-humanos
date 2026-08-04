"""
Desactiva un empleado y lo mueve al subgrupo de RETIRADOS elegido por el
usuario.

A diferencia de la versión anterior (que intentaba adivinar el subgrupo de
Retirados a partir de la zona del empleado), ahora el destino lo decide
explícitamente quien opera: se recibe `retirement_group_id` y se valida que
ese grupo exista y sea hijo del grupo raíz "RETIRADOS".

Efectos:
  - Mueve la carpeta de Drive del empleado al drive_folder_id del destino.
  - Actualiza employee.group_id al grupo de destino.
  - Marca employee.is_active = False.

Nota sobre reactivación: `reactivate_employee` solo cambia is_active=True.
No mueve la carpeta de vuelta ni restaura el group_id original porque esa
información ya no está disponible en el dominio.
"""
from __future__ import annotations

import unicodedata
from uuid import UUID

from domain.exceptions import DomainError, EmployeeNotFoundError, GroupNotFoundError
from domain.ports.employee_repository import EmployeeRepository
from domain.ports.file_storage import FileStorage
from domain.ports.group_repository import GroupRepository

_RETIRADOS_ROOT_NAME = "RETIRADOS"


def _normalize(text: str) -> str:
    """MAYÚSCULAS y sin tildes, para comparar nombres de grupo de forma robusta."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().upper()


class InvalidRetirementGroupError(DomainError):
    def __init__(self, group_id: UUID) -> None:
        super().__init__(
            f"El grupo '{group_id}' no es un subgrupo válido de RETIRADOS."
        )
        self.group_id = group_id


class DeactivateEmployee:

    def __init__(
        self,
        employee_repo: EmployeeRepository,
        group_repo: GroupRepository,
        file_storage: FileStorage,
    ) -> None:
        self._employee_repo = employee_repo
        self._group_repo = group_repo
        self._file_storage = file_storage

    def execute(self, employee_id: UUID, retirement_group_id: UUID) -> None:
        employee = self._employee_repo.get_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundError(employee_id)

        # ── Validar el grupo de destino ───────────────────────────────────
        target_group = self._group_repo.get_by_id(retirement_group_id)
        if target_group is None:
            raise GroupNotFoundError(retirement_group_id)

        # Debe ser hijo del grupo raíz cuyo nombre normalizado es "RETIRADOS".
        if target_group.parent_id is None:
            raise InvalidRetirementGroupError(retirement_group_id)
        parent = self._group_repo.get_by_id(target_group.parent_id)
        if parent is None or _normalize(parent.name) != _RETIRADOS_ROOT_NAME:
            raise InvalidRetirementGroupError(retirement_group_id)

        # ── Carpeta actual del empleado (grupo nivel 2 de origen) ─────────
        current_folder_id: str | None = None
        if employee.group_id:
            current_group = self._group_repo.get_by_id(employee.group_id)
            if current_group:
                current_folder_id = current_group.drive_folder_id

        # ── Mover carpeta en Drive ────────────────────────────────────────
        if current_folder_id and target_group.drive_folder_id:
            try:
                self._file_storage.move_folder(
                    folder_name=employee.name,
                    from_parent_id=current_folder_id,
                    to_parent_id=target_group.drive_folder_id,
                )
            except Exception:
                pass  # fallo de Drive no impide la desactivación en BD

        # ── Actualizar empleado en BD ─────────────────────────────────────
        employee.group_id = target_group.id
        employee.is_active = False
        self._employee_repo.update(employee)
