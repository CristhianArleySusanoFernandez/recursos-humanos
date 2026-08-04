"""
Subida masiva de una carpeta de archivos de un mismo empleado,
con clasificación automática vía DocumentClassifier (Ollama).

A diferencia de UploadDocument (subida individual), este caso de uso:
  - No recibe el tipo de documento: lo deduce.
  - NO reemplaza documentos existentes: los omite.
  - Nunca aborta el lote por un error puntual: acumula y continúa.

Archivos sin categoría
----------------------
La tabla documents tiene UNIQUE(employee_id, document_type_id), así que un
único tipo "EXTRA" compartido solo admitiría un archivo sin clasificar por
empleado. En su lugar se crea un tipo por archivo, con código derivado del
nombre (EXTRA_<md5[:8]>), de modo que cada archivo extra ocupa su propia
fila y se muestra en la app con su nombre real.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from domain.entities.document import Document
from domain.entities.document_type import EXTRA_CATEGORY, DocumentType
from domain.exceptions import EmployeeNotFoundError, InactiveEmployeeError
from domain.ports.document_classifier import DocumentClassifier
from domain.ports.document_repository import DocumentRepository
from domain.ports.document_type_repository import DocumentTypeRepository
from domain.ports.employee_repository import EmployeeRepository
from domain.ports.file_storage import FileStorage
from domain.ports.group_repository import GroupRepository

_EXTRA_PREFIX = "EXTRA_"
_EXTRA_NAME_MAX_LEN = 100


@dataclass
class BulkUploadInput:
    employee_id: UUID
    files: list[tuple[str, bytes, str]]  # (filename, content, mime_type)


@dataclass
class BulkUploadResult:
    total: int = 0
    clasificados: list[tuple[str, str]] = field(default_factory=list)  # (filename, code)
    omitidos: list[str] = field(default_factory=list)                  # ya existían
    extras: list[str] = field(default_factory=list)                    # quedaron como EXTRA
    errores: list[tuple[str, str]] = field(default_factory=list)       # (filename, mensaje)


def _build_drive_filename(code: str, employee_name: str, original_name: str) -> str:
    """Nombre canónico en Drive: CODE_NombreEmpleado.ext"""
    _, _, ext = original_name.rpartition(".")
    safe_name = employee_name.strip().replace(" ", "_")
    return f"{code}_{safe_name}.{ext}" if ext else f"{code}_{safe_name}"


def _extra_code(filename: str) -> str:
    """Código estable y único por nombre de archivo: EXTRA_<md5[:8]>."""
    digest = hashlib.md5(filename.encode("utf-8")).hexdigest()[:8]
    return f"{_EXTRA_PREFIX}{digest.upper()}"


class BulkUpload:

    def __init__(
        self,
        classifier: DocumentClassifier,
        file_storage: FileStorage,
        employee_repo: EmployeeRepository,
        document_repo: DocumentRepository,
        document_type_repo: DocumentTypeRepository,
        group_repo: GroupRepository,
    ) -> None:
        self._classifier = classifier
        self._file_storage = file_storage
        self._employee_repo = employee_repo
        self._document_repo = document_repo
        self._document_type_repo = document_type_repo
        self._group_repo = group_repo

    def execute(self, input: BulkUploadInput) -> BulkUploadResult:
        employee = self._employee_repo.get_by_id(input.employee_id)
        if employee is None:
            raise EmployeeNotFoundError(input.employee_id)
        if not employee.is_active:
            raise InactiveEmployeeError(input.employee_id)

        # Carpeta de Drive del grupo — se resuelve una sola vez para todo el lote.
        group_drive_folder_id: str | None = None
        if employee.group_id is not None:
            group = self._group_repo.get_by_id(employee.group_id)
            if group is not None:
                group_drive_folder_id = group.drive_folder_id

        result = BulkUploadResult(total=len(input.files))

        for filename, content, mime_type in input.files:
            try:
                self._process_one(
                    filename=filename,
                    content=content,
                    mime_type=mime_type,
                    employee_name=employee.name,
                    employee_id=input.employee_id,
                    group_drive_folder_id=group_drive_folder_id,
                    result=result,
                )
            except Exception as exc:
                # Un archivo fallido nunca aborta el lote.
                result.errores.append((filename, str(exc)))

        return result

    # ------------------------------------------------------------------

    def _process_one(
        self,
        filename: str,
        content: bytes,
        mime_type: str,
        employee_name: str,
        employee_id: UUID,
        group_drive_folder_id: str | None,
        result: BulkUploadResult,
    ) -> None:
        # 1. Clasificar. El clasificador nunca lanza: retorna None si falla.
        doc_type = self._classifier.classify(content, filename, mime_type)

        is_extra = doc_type is None
        if is_extra:
            doc_type = self._get_or_create_extra_type(filename)

        # 2. No sobreescribir un documento ya registrado de ese tipo.
        existing = self._document_repo.get_by_employee_and_type(employee_id, doc_type.id)
        if existing is not None:
            result.omitidos.append(filename)
            return

        # 3. Subir a Drive.
        drive_file_name = _build_drive_filename(doc_type.code, employee_name, filename)
        uploaded = self._file_storage.upload(
            file_content=content,
            file_name=drive_file_name,
            mime_type=mime_type,
            employee_name=employee_name,
            group_drive_folder_id=group_drive_folder_id,
        )

        # 4. Registrar en BD.
        self._document_repo.save(Document.create(
            employee_id=employee_id,
            document_type_id=doc_type.id,
            file_name=drive_file_name,
            drive_file_id=uploaded.file_id,
            drive_url=uploaded.url,
        ))

        if is_extra:
            result.extras.append(filename)
        else:
            result.clasificados.append((filename, doc_type.code))

    # ------------------------------------------------------------------

    def _get_or_create_extra_type(self, filename: str) -> DocumentType:
        """
        Devuelve el tipo dedicado a este archivo sin clasificar, creándolo
        si es la primera vez que se ve ese nombre de archivo.
        """
        code = _extra_code(filename)

        existing = self._document_type_repo.get_by_code(code)
        if existing is not None:
            return existing

        doc_type = DocumentType(
            id=uuid4(),
            name=filename[:_EXTRA_NAME_MAX_LEN],
            code=code,
            category=EXTRA_CATEGORY,
            is_active=True,
            order_index=99,
            created_at=datetime.now(timezone.utc),
        )
        self._document_type_repo.save(doc_type)
        return doc_type
