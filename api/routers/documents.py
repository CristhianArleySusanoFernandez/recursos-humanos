from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from api.dependencies import (
    get_bulk_upload,
    get_delete_document,
    get_document_classifier,
    get_toggle_document_na,
    get_upload_document,
)
from application.use_cases.bulk_upload import BulkUpload, BulkUploadInput
from application.use_cases.delete_document import DeleteDocument
from application.use_cases.toggle_document_na import ToggleDocumentNa, ToggleDocumentNaInput
from application.use_cases.upload_document import UploadDocument, UploadDocumentInput
from domain.exceptions import DomainError
from infrastructure.ollama.document_classifier import OllamaDocumentClassifier

router = APIRouter()

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _url_encode(text: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(text)


# ---------------------------------------------------------------------------
# Subir documento
# ---------------------------------------------------------------------------


@router.post("/{employee_id}/upload")
async def upload_document(
    employee_id: UUID,
    document_type_id: str = Form(...),
    file: UploadFile = File(...),
    use_case: UploadDocument = Depends(get_upload_document),
):
    detail_url = f"/{employee_id}#documentos"

    try:
        doc_type_uuid = UUID(document_type_id)
    except ValueError:
        return RedirectResponse(
            url=f"/{employee_id}?error=ID+de+tipo+de+documento+no+válido#documentos",
            status_code=303,
        )

    if file.content_type not in _ALLOWED_MIME_TYPES:
        return RedirectResponse(
            url=f"/{employee_id}?error=Tipo+de+archivo+no+permitido+({file.content_type})#documentos",
            status_code=303,
        )

    file_content = await file.read()

    try:
        use_case.execute(UploadDocumentInput(
            employee_id=employee_id,
            document_type_id=doc_type_uuid,
            file_content=file_content,
            file_name=file.filename or "documento",
            mime_type=file.content_type or "application/octet-stream",
        ))
    except DomainError as exc:
        return RedirectResponse(
            url=f"/{employee_id}?error={_url_encode(str(exc))}#documentos",
            status_code=303,
        )

    return RedirectResponse(url=detail_url, status_code=303)


# ---------------------------------------------------------------------------
# Estado de Ollama — usado por detail.html al cargar la página
# ---------------------------------------------------------------------------
# Nota: la ruta tiene 2 segmentos, por lo que no colisiona con el patrón
# dinámico /{employee_id} del router de empleados.


@router.get("/api/ollama-status")
async def ollama_status(
    classifier: OllamaDocumentClassifier = Depends(get_document_classifier),
):
    return JSONResponse({"available": classifier.is_available()})


# ---------------------------------------------------------------------------
# Subida masiva con clasificación automática
# ---------------------------------------------------------------------------


@router.post("/{employee_id}/bulk-upload")
async def bulk_upload_documents(
    employee_id: UUID,
    files: list[UploadFile] = File(...),
    use_case: BulkUpload = Depends(get_bulk_upload),
):
    payload: list[tuple[str, bytes, str]] = []
    for f in files:
        content = await f.read()
        payload.append((
            f.filename or "documento",
            content,
            f.content_type or "application/octet-stream",
        ))

    try:
        result = use_case.execute(BulkUploadInput(
            employee_id=employee_id,
            files=payload,
        ))
    except DomainError as exc:
        return RedirectResponse(
            url=f"/{employee_id}?error={_url_encode(str(exc))}#subida-masiva",
            status_code=303,
        )

    summary = (
        f"{len(result.clasificados)}_clasificados,"
        f"{len(result.extras)}_extras,"
        f"{len(result.errores)}_errores,"
        f"{len(result.omitidos)}_omitidos"
    )
    return RedirectResponse(
        url=f"/{employee_id}?bulk_result={_url_encode(summary)}#subida-masiva",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Toggle N/A — retorna JSON para fetch()
# ---------------------------------------------------------------------------


@router.post("/{employee_id}/documents/{document_type_id}/na/toggle")
async def toggle_document_na(
    employee_id: UUID,
    document_type_id: UUID,
    use_case: ToggleDocumentNa = Depends(get_toggle_document_na),
):
    try:
        is_na_now = use_case.execute(ToggleDocumentNaInput(
            employee_id=employee_id,
            document_type_id=document_type_id,
        ))
        return JSONResponse({"ok": True, "is_na": is_na_now})
    except DomainError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Eliminar documento — retorna JSON para fetch()
# ---------------------------------------------------------------------------


@router.post("/{employee_id}/documents/{document_type_id}/delete")
async def delete_document(
    employee_id: UUID,
    document_type_id: UUID,
    use_case: DeleteDocument = Depends(get_delete_document),
):
    try:
        use_case.execute(employee_id=employee_id, document_type_id=document_type_id)
        return JSONResponse({"ok": True})
    except DomainError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
