from dataclasses import dataclass
from uuid import UUID

from domain.entities.document import Document
from domain.entities.document_type import EXTRA_CATEGORY, DocumentType
from domain.entities.employee import Employee
from domain.exceptions import EmployeeNotFoundError
from domain.ports.document_na_repository import DocumentNaRepository
from domain.ports.document_repository import DocumentRepository
from domain.ports.document_type_repository import DocumentTypeRepository
from domain.ports.employee_repository import EmployeeRepository

from application.use_cases._shared import normalize_name_key


@dataclass
class EmployeeChecklist:
    employee: Employee
    document_types: list[DocumentType]
    # 3-tupla: (tipo, documento_subido | None, es_na)
    ingreso_pairs: list[tuple[DocumentType, Document | None, bool]]
    retiro_pairs: list[tuple[DocumentType, Document | None, bool]]
    # Archivos adicionales de la subida masiva. Siempre existe el documento:
    # un tipo EXTRA solo se crea al registrar su archivo.
    extra_documents: list[tuple[DocumentType, Document]]
    # (presentes_o_na, total_requeridos) — no incluye EXTRA
    completion_ratio: tuple[int, int]


class GetEmployeeChecklist:

    def __init__(
        self,
        employee_repo: EmployeeRepository,
        document_repo: DocumentRepository,
        document_type_repo: DocumentTypeRepository,
        document_na_repo: DocumentNaRepository,
    ) -> None:
        self._employee_repo = employee_repo
        self._document_repo = document_repo
        self._document_type_repo = document_type_repo
        self._document_na_repo = document_na_repo

    def execute(self, employee_id: UUID) -> EmployeeChecklist:
        employee = self._employee_repo.get_by_id(employee_id)
        if employee is None:
            raise EmployeeNotFoundError(employee_id)

        employee.documents = self._document_repo.get_by_employee(employee_id)
        na_type_ids = self._document_na_repo.get_na_type_ids(employee_id)

        all_types = sorted(
            self._document_type_repo.list_active(),
            key=lambda dt: (dt.category, normalize_name_key(dt.name)),
        )

        # Los tipos EXTRA se separan: no son documentos requeridos, así que
        # quedan fuera del checklist y del ratio de completitud.
        required_types = [dt for dt in all_types if dt.category != EXTRA_CATEGORY]

        def _with_na(raw: list[tuple[DocumentType, Document | None]]):
            return [(dt, doc, dt.id in na_type_ids) for dt, doc in raw]

        ingreso_pairs = _with_na(employee.get_documents_by_category("INGRESO", required_types))
        retiro_pairs = _with_na(employee.get_documents_by_category("RETIRO", required_types))
        extra_documents = employee.get_extra_documents(all_types)

        # N/A cuenta como "atendido" — excluye el documento del total de faltantes.
        doc_ids_present = {d.document_type_id for d in employee.documents}
        required_ids = [dt.id for dt in required_types]
        present_or_na = sum(
            1 for dt_id in required_ids
            if dt_id in doc_ids_present or dt_id in na_type_ids
        )
        ratio = (present_or_na, len(required_ids))

        return EmployeeChecklist(
            employee=employee,
            document_types=required_types,
            ingreso_pairs=ingreso_pairs,
            retiro_pairs=retiro_pairs,
            extra_documents=extra_documents,
            completion_ratio=ratio,
        )
