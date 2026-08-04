from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from api.dependencies import (
    get_create_document_type,
    get_list_document_types,
    get_update_document_type,
)
from api.templating import templates
from application.use_cases.create_document_type import CreateDocumentType, CreateDocumentTypeInput
from application.use_cases.list_document_types import ListDocumentTypes
from application.use_cases.update_document_type import UpdateDocumentType, UpdateDocumentTypeInput
from domain.exceptions import DomainError

router = APIRouter(prefix="/document-types")


def _url_encode(text: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(text)


# ---------------------------------------------------------------------------
# Lista de tipos de documento
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def list_document_types(
    request: Request,
    use_case: ListDocumentTypes = Depends(get_list_document_types),
    error: str | None = None,
):
    document_types = use_case.execute()
    return templates.TemplateResponse("document_types/list.html", {
        "request": request,
        "document_types": document_types,
        "error": error,
    })


# ---------------------------------------------------------------------------
# Crear tipo de documento
# ---------------------------------------------------------------------------


@router.post("")
async def create_document_type(
    request: Request,
    name: str = Form(...),
    code: str = Form(...),
    category: str = Form(...),
    order_index: int = Form(...),
    use_case: CreateDocumentType = Depends(get_create_document_type),
    list_uc: ListDocumentTypes = Depends(get_list_document_types),
):
    try:
        use_case.execute(CreateDocumentTypeInput(
            name=name,
            code=code,
            category=category,
            order_index=order_index,
        ))
    except (DomainError, ValueError) as exc:
        document_types = list_uc.execute()
        return templates.TemplateResponse("document_types/list.html", {
            "request": request,
            "document_types": document_types,
            "error": str(exc),
        }, status_code=422)
    return RedirectResponse(url="/document-types", status_code=303)


# ---------------------------------------------------------------------------
# Editar tipo de documento
# ---------------------------------------------------------------------------


@router.post("/{document_type_id}/edit")
async def edit_document_type(
    document_type_id: UUID,
    name: str = Form(None),
    is_active: str = Form(None),
    order_index: str = Form(None),
    use_case: UpdateDocumentType = Depends(get_update_document_type),
):
    # Los checkboxes HTML no envían valor cuando están desmarcados;
    # convertimos explícitamente el string a bool solo si vino en el form.
    is_active_bool: bool | None = None
    if is_active is not None:
        is_active_bool = is_active.lower() in ("1", "true", "on", "yes")

    order_index_int: int | None = None
    if order_index is not None and order_index.strip():
        try:
            order_index_int = int(order_index)
        except ValueError:
            return RedirectResponse(
                url=f"/document-types?error=order_index+debe+ser+un+número+entero",
                status_code=303,
            )

    try:
        use_case.execute(UpdateDocumentTypeInput(
            document_type_id=document_type_id,
            name=name if name and name.strip() else None,
            is_active=is_active_bool,
            order_index=order_index_int,
        ))
    except DomainError as exc:
        return RedirectResponse(
            url=f"/document-types?error={_url_encode(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(url="/document-types", status_code=303)
