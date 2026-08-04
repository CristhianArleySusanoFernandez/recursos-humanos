"""
Composición de adaptadores y casos de uso para FastAPI.

Cada función get_* es una dependencia inyectable via Depends().
GoogleDriveAdapter se cachea con lru_cache porque autentica en __init__.
Los repositorios de Supabase son ligeros: comparten el cliente singleton interno.
"""

from fastapi import Depends

from application.use_cases.bulk_upload import BulkUpload
from application.use_cases.create_document_type import CreateDocumentType
from application.use_cases.create_employee import CreateEmployee
from application.use_cases.deactivate_employee import DeactivateEmployee
from application.use_cases.create_group import CreateGroup
from application.use_cases.delete_document import DeleteDocument
from application.use_cases.delete_employee import DeleteEmployee
from application.use_cases.toggle_document_na import ToggleDocumentNa
from application.use_cases.delete_group import DeleteGroup
from application.use_cases.get_employee_checklist import GetEmployeeChecklist
from application.use_cases.list_document_types import ListDocumentTypes
from application.use_cases.list_documents_for_review import ListDocumentsForReview
from application.use_cases.list_employees import ListEmployees
from application.use_cases.list_groups import ListGroups
from application.use_cases.reclassify_document import ReclassifyDocument
from application.use_cases.update_document_type import UpdateDocumentType
from application.use_cases.update_employee import UpdateEmployee
from application.use_cases.update_group import UpdateGroup
from application.use_cases.upload_document import UploadDocument
from infrastructure.google_drive.drive_adapter import GoogleDriveAdapter
from infrastructure.ollama.document_classifier import OllamaDocumentClassifier
from infrastructure.supabase.document_na_repository import SupabaseDocumentNaRepository
from infrastructure.supabase.document_repository import SupabaseDocumentRepository
from infrastructure.supabase.document_type_repository import SupabaseDocumentTypeRepository
from infrastructure.supabase.employee_repository import SupabaseEmployeeRepository
from infrastructure.supabase.group_repository import SupabaseGroupRepository

# ---------------------------------------------------------------------------
# Adaptadores de infraestructura pesados (singletons)
# ---------------------------------------------------------------------------


def get_drive_adapter() -> GoogleDriveAdapter:
    return GoogleDriveAdapter()


def get_document_classifier() -> OllamaDocumentClassifier:
    """
    Clasificador local vía Ollama. No requiere API key.
    Es ligero de instanciar: solo guarda la URL base y el modelo.
    """
    return OllamaDocumentClassifier(SupabaseDocumentTypeRepository())


# ---------------------------------------------------------------------------
# Repositorios (ligeros; el cliente Supabase es singleton internamente)
# ---------------------------------------------------------------------------


def get_employee_repo() -> SupabaseEmployeeRepository:
    return SupabaseEmployeeRepository()


def get_document_repo() -> SupabaseDocumentRepository:
    return SupabaseDocumentRepository()


def get_document_na_repo() -> SupabaseDocumentNaRepository:
    return SupabaseDocumentNaRepository()


def get_document_type_repo() -> SupabaseDocumentTypeRepository:
    return SupabaseDocumentTypeRepository()


def get_group_repo() -> SupabaseGroupRepository:
    return SupabaseGroupRepository()


# ---------------------------------------------------------------------------
# Casos de uso — empleados
# ---------------------------------------------------------------------------


def get_delete_employee(
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
    document_repo: SupabaseDocumentRepository = Depends(get_document_repo),
    file_storage: GoogleDriveAdapter = Depends(get_drive_adapter),
) -> DeleteEmployee:
    return DeleteEmployee(employee_repo, document_repo, file_storage)


def get_deactivate_employee(
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
    file_storage: GoogleDriveAdapter = Depends(get_drive_adapter),
) -> DeactivateEmployee:
    return DeactivateEmployee(employee_repo, group_repo, file_storage)


def get_create_employee(
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
) -> CreateEmployee:
    return CreateEmployee(employee_repo, group_repo)


def get_update_employee(
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
) -> UpdateEmployee:
    return UpdateEmployee(employee_repo, group_repo)


def get_list_employees(
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
    document_repo: SupabaseDocumentRepository = Depends(get_document_repo),
) -> ListEmployees:
    return ListEmployees(employee_repo, document_repo)


def get_employee_checklist(
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
    document_repo: SupabaseDocumentRepository = Depends(get_document_repo),
    document_type_repo: SupabaseDocumentTypeRepository = Depends(get_document_type_repo),
    document_na_repo: SupabaseDocumentNaRepository = Depends(get_document_na_repo),
) -> GetEmployeeChecklist:
    return GetEmployeeChecklist(employee_repo, document_repo, document_type_repo, document_na_repo)


# ---------------------------------------------------------------------------
# Casos de uso — documentos
# ---------------------------------------------------------------------------


def get_upload_document(
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
    document_repo: SupabaseDocumentRepository = Depends(get_document_repo),
    document_type_repo: SupabaseDocumentTypeRepository = Depends(get_document_type_repo),
    file_storage: GoogleDriveAdapter = Depends(get_drive_adapter),
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
) -> UploadDocument:
    return UploadDocument(employee_repo, document_repo, document_type_repo, file_storage, group_repo)


def get_bulk_upload(
    classifier: OllamaDocumentClassifier = Depends(get_document_classifier),
    file_storage: GoogleDriveAdapter = Depends(get_drive_adapter),
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
    document_repo: SupabaseDocumentRepository = Depends(get_document_repo),
    document_type_repo: SupabaseDocumentTypeRepository = Depends(get_document_type_repo),
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
) -> BulkUpload:
    return BulkUpload(
        classifier,
        file_storage,
        employee_repo,
        document_repo,
        document_type_repo,
        group_repo,
    )


def get_delete_document(
    document_repo: SupabaseDocumentRepository = Depends(get_document_repo),
    file_storage: GoogleDriveAdapter = Depends(get_drive_adapter),
) -> DeleteDocument:
    return DeleteDocument(document_repo, file_storage)


def get_toggle_document_na(
    document_na_repo: SupabaseDocumentNaRepository = Depends(get_document_na_repo),
) -> ToggleDocumentNa:
    return ToggleDocumentNa(document_na_repo)


def get_reclassify_document(
    document_repo: SupabaseDocumentRepository = Depends(get_document_repo),
    document_type_repo: SupabaseDocumentTypeRepository = Depends(get_document_type_repo),
    file_storage: GoogleDriveAdapter = Depends(get_drive_adapter),
) -> ReclassifyDocument:
    return ReclassifyDocument(document_repo, document_type_repo, file_storage)


def get_list_documents_for_review(
    document_repo: SupabaseDocumentRepository = Depends(get_document_repo),
    document_type_repo: SupabaseDocumentTypeRepository = Depends(get_document_type_repo),
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
) -> ListDocumentsForReview:
    return ListDocumentsForReview(
        document_repo, document_type_repo, employee_repo, group_repo
    )


# ---------------------------------------------------------------------------
# Casos de uso — grupos
# ---------------------------------------------------------------------------


def get_create_group(
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
    file_storage: GoogleDriveAdapter = Depends(get_drive_adapter),
) -> CreateGroup:
    return CreateGroup(group_repo, file_storage)


def get_update_group(
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
) -> UpdateGroup:
    return UpdateGroup(group_repo)


def get_delete_group(
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
) -> DeleteGroup:
    return DeleteGroup(group_repo, employee_repo)


def get_list_groups(
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
) -> ListGroups:
    return ListGroups(group_repo)


# ---------------------------------------------------------------------------
# Casos de uso — tipos de documento
# ---------------------------------------------------------------------------


def get_list_document_types(
    document_type_repo: SupabaseDocumentTypeRepository = Depends(get_document_type_repo),
) -> ListDocumentTypes:
    return ListDocumentTypes(document_type_repo)


def get_create_document_type(
    document_type_repo: SupabaseDocumentTypeRepository = Depends(get_document_type_repo),
) -> CreateDocumentType:
    return CreateDocumentType(document_type_repo)


def get_update_document_type(
    document_type_repo: SupabaseDocumentTypeRepository = Depends(get_document_type_repo),
) -> UpdateDocumentType:
    return UpdateDocumentType(document_type_repo)
