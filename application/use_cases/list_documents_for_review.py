"""
Construye la cola de revisión para la pantalla "Recategorizar documentos".

Devuelve un DocumentReviewItem por cada documento existente, con los datos que
la UI necesita para mostrarlo (empleado, ruta de grupo, archivo, tipo actual).

Filtros:
  - only_extra=True  → solo documentos cuyo tipo tiene category='EXTRA'.
  - group_id=X       → solo documentos de empleados que cuelgan de la zona X
                       (coincide con la zona raíz o cualquiera de sus subgrupos).
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from domain.entities.document_type import EXTRA_CATEGORY
from domain.entities.group import Group
from domain.ports.document_repository import DocumentRepository
from domain.ports.document_type_repository import DocumentTypeRepository
from domain.ports.employee_repository import EmployeeRepository
from domain.ports.group_repository import GroupRepository

from perf_debug import log, timed  # [PERF-DEBUG] instrumentación temporal


@dataclass
class DocumentReviewItem:
    document_id: UUID
    employee_id: UUID
    employee_name: str
    employee_group_path: str          # ej: "TUNJA / ASESORES"
    file_name: str
    drive_url: str
    current_document_type_id: UUID
    current_document_type_name: str


@dataclass
class ListDocumentsForReviewInput:
    only_extra: bool = False
    group_id: UUID | None = None


class ListDocumentsForReview:

    def __init__(
        self,
        document_repo: DocumentRepository,
        document_type_repo: DocumentTypeRepository,
        employee_repo: EmployeeRepository,
        group_repo: GroupRepository,
    ) -> None:
        self._document_repo = document_repo
        self._document_type_repo = document_type_repo
        self._employee_repo = employee_repo
        self._group_repo = group_repo

    def execute(self, data: ListDocumentsForReviewInput) -> list[DocumentReviewItem]:
        # [PERF-DEBUG] query de tipos de documento.
        with timed("ListDocsForReview: query tipos (list_all)"):
            types_by_id = {dt.id: dt for dt in self._document_type_repo.list_all()}

        # [PERF-DEBUG] DOS queries: empleados activos + inactivos.
        with timed("ListDocsForReview: query empleados (activos + inactivos = 2 queries)"):
            employees_by_id = {
                e.id: e
                for e in (
                    self._employee_repo.list_all(active_only=True)
                    + self._employee_repo.list_all(active_only=False)
                )
            }

        # [PERF-DEBUG] query de grupos (aplanado del árbol).
        with timed("ListDocsForReview: query grupos (flatten)"):
            groups_by_id = self._flatten_groups()

        # [PERF-DEBUG] paginación de TODOS los documentos (varias queries de 1000).
        with timed("ListDocsForReview: query documentos (list_all paginado)"):
            all_docs = self._document_repo.list_all()
        log(f"ListDocsForReview: {len(all_docs)} documentos, "
            f"{len(employees_by_id)} empleados, {len(types_by_id)} tipos")

        # [PERF-DEBUG] armado de la cola en Python (sin tocar red).
        with timed(f"ListDocsForReview: armado en Python sobre {len(all_docs)} docs"):
            items: list[DocumentReviewItem] = []
            for doc in all_docs:
                dtype = types_by_id.get(doc.document_type_id)
                if dtype is None:
                    continue  # tipo huérfano: se ignora en la cola

                if data.only_extra and dtype.category != EXTRA_CATEGORY:
                    continue

                employee = employees_by_id.get(doc.employee_id)
                if employee is None:
                    continue

                if data.group_id is not None and not self._in_group_subtree(
                    employee.group_id, data.group_id, groups_by_id
                ):
                    continue

                items.append(DocumentReviewItem(
                    document_id=doc.id,
                    employee_id=doc.employee_id,
                    employee_name=employee.name,
                    employee_group_path=self._group_path(employee.group_id, groups_by_id),
                    file_name=doc.file_name,
                    drive_url=doc.drive_url,
                    current_document_type_id=doc.document_type_id,
                    current_document_type_name=dtype.name,
                ))

            items.sort(key=lambda it: it.employee_name.upper())
        log(f"ListDocsForReview: {len(items)} items resultantes")
        return items

    # ------------------------------------------------------------------
    # Helpers de grupos
    # ------------------------------------------------------------------

    def _flatten_groups(self) -> dict[UUID, Group]:
        """Mapa id→Group (árbol aplanado a partir de list_all)."""
        flat: dict[UUID, Group] = {}

        def walk(groups: list[Group]) -> None:
            for g in groups:
                flat[g.id] = g
                if g.children:
                    walk(g.children)

        walk(self._group_repo.list_all())
        return flat

    def _group_path(self, group_id: UUID | None, groups: dict[UUID, Group]) -> str:
        """Ruta 'Zona / Subgrupo' subiendo por parent_id."""
        names: list[str] = []
        seen: set[UUID] = set()
        current = groups.get(group_id) if group_id else None
        while current and current.id not in seen:
            seen.add(current.id)
            names.append(current.name)
            current = groups.get(current.parent_id) if current.parent_id else None
        return " / ".join(reversed(names)) if names else "(sin grupo)"

    def _in_group_subtree(
        self, group_id: UUID | None, target_id: UUID, groups: dict[UUID, Group]
    ) -> bool:
        """True si target_id es el grupo del empleado o un ancestro suyo."""
        seen: set[UUID] = set()
        current = groups.get(group_id) if group_id else None
        while current and current.id not in seen:
            if current.id == target_id:
                return True
            seen.add(current.id)
            current = groups.get(current.parent_id) if current.parent_id else None
        return False
