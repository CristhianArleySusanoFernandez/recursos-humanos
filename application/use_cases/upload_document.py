from dataclasses import dataclass
from uuid import UUID

from domain.entities.document import Document
from domain.exceptions import (
    DocumentTypeNotFoundError,
    EmployeeNotFoundError,
    InactiveEmployeeError,
)
from domain.ports.document_repository import DocumentRepository
from domain.ports.document_type_repository import DocumentTypeRepository
from domain.ports.employee_repository import EmployeeRepository
from domain.ports.file_storage import FileStorage
from domain.ports.group_repository import GroupRepository


@dataclass
class UploadDocumentInput:
    employee_id: UUID
    document_type_id: UUID
    file_content: bytes
    file_name: str
    mime_type: str


def _build_drive_filename(code: str, employee_name: str, original_name: str) -> str:
    """Construye el nombre canónico del archivo en Drive: CODE_NombreEmpleado.ext"""
    _, _, ext = original_name.rpartition(".")
    safe_name = employee_name.strip().replace(" ", "_")
    return f"{code}_{safe_name}.{ext}" if ext else f"{code}_{safe_name}"


class UploadDocument:

    def __init__(
        self,
        employee_repo: EmployeeRepository,
        document_repo: DocumentRepository,
        document_type_repo: DocumentTypeRepository,
        file_storage: FileStorage,
        group_repo: GroupRepository,
    ) -> None:
        self._employee_repo = employee_repo
        self._document_repo = document_repo
        self._document_type_repo = document_type_repo
        self._file_storage = file_storage
        self._group_repo = group_repo

    def execute(self, input: UploadDocumentInput) -> None:
        employee = self._employee_repo.get_by_id(input.employee_id)
        if employee is None:
            raise EmployeeNotFoundError(input.employee_id)
        if not employee.is_active:
            raise InactiveEmployeeError(input.employee_id)

        doc_type = self._document_type_repo.get_by_id(input.document_type_id)
        if doc_type is None or not doc_type.is_active:
            raise DocumentTypeNotFoundError(str(input.document_type_id))

        # Si ya existe un documento del mismo tipo, elimina el anterior.
        existing = self._document_repo.get_by_employee_and_type(
            input.employee_id, input.document_type_id
        )
        if existing is not None:
            self._file_storage.delete(existing.drive_file_id)
            self._document_repo.delete(input.employee_id, input.document_type_id)

        drive_file_name = _build_drive_filename(
            doc_type.code, employee.name, input.file_name
        )

        # Resuelve la carpeta del grupo si el empleado tiene uno asignado.
        group_drive_folder_id: str | None = None
        if employee.group_id is not None:
            group = self._group_repo.get_by_id(employee.group_id)
            if group is not None:
                group_drive_folder_id = group.drive_folder_id

        uploaded = self._file_storage.upload(
            file_content=input.file_content,
            file_name=drive_file_name,
            mime_type=input.mime_type,
            employee_name=employee.name,
            group_drive_folder_id=group_drive_folder_id,
        )

        document = Document.create(
            employee_id=input.employee_id,
            document_type_id=input.document_type_id,
            file_name=drive_file_name,
            drive_file_id=uploaded.file_id,
            drive_url=uploaded.url,
        )
        self._document_repo.save(document)
