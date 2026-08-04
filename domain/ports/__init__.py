# Re-exporta los puertos (interfaces abstractas) del dominio.
from .employee_repository import EmployeeRepository
from .document_repository import DocumentRepository
from .document_type_repository import DocumentTypeRepository
from .group_repository import GroupRepository
from .file_storage import FileStorage
from .document_na_repository import DocumentNaRepository

__all__ = [
    "EmployeeRepository",
    "DocumentRepository",
    "DocumentTypeRepository",
    "GroupRepository",
    "FileStorage",
    "DocumentNaRepository",
]
