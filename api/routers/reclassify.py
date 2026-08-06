"""
Pantalla "Recategorizar documentos": cola de revisión para reasignar el tipo
de cualquier documento ya subido (no solo los EXTRA).

Rutas (registradas ANTES del router de empleados en main.py, porque /reclassify
es estática y colisionaría con el patrón dinámico GET /{employee_id}):

  GET  /reclassify                     → página HTML con la cola precargada
  GET  /reclassify/list                → JSON de pendientes (recarga por filtros)
  GET  /reclassify/search-employees    → JSON autocompletar de empleados
  POST /reclassify/{document_id}       → aplica el cambio; JSON {ok} o {conflict}
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from api.dependencies import (
    get_document_repo,
    get_document_type_repo,
    get_employee_repo,
    get_group_repo,
    get_list_documents_for_review,
    get_list_groups,
    get_reclassify_document,
)
from infrastructure.supabase.employee_repository import SupabaseEmployeeRepository
from infrastructure.supabase.group_repository import SupabaseGroupRepository
from application.use_cases._shared import (
    EXTRA_AUTO_SENTINEL,
    get_or_create_extra_type,
    normalize_name_key,
)
from infrastructure.supabase.document_repository import SupabaseDocumentRepository
from api.templating import templates
from application.use_cases.list_documents_for_review import (
    DocumentReviewItem,
    ListDocumentsForReview,
    ListDocumentsForReviewInput,
)
from application.use_cases.list_groups import ListGroups
from application.use_cases.reclassify_document import (
    STATUS_CONFLICT,
    ReclassifyDocument,
    ReclassifyDocumentInput,
)
from domain.exceptions import DomainError
from infrastructure.supabase.document_type_repository import (
    SupabaseDocumentTypeRepository,
)

router = APIRouter()


def _preview_url(drive_url: str) -> str:
    """Convierte la URL /view de Drive en /preview (embebible en iframe)."""
    return (drive_url or "").replace("/view", "/preview")


def _item_to_dict(item: DocumentReviewItem) -> dict:
    return {
        "document_id": str(item.document_id),
        "employee_id": str(item.employee_id),
        "employee_name": item.employee_name,
        "employee_group_path": item.employee_group_path,
        "file_name": item.file_name,
        "drive_url": item.drive_url,
        "preview_url": _preview_url(item.drive_url),
        "current_document_type_id": str(item.current_document_type_id),
        "current_document_type_name": item.current_document_type_name,
        "verified": item.verified,
    }


def _collect_items(
    list_uc: ListDocumentsForReview,
    only_extra: bool,
    group_id: UUID | None,
    employee_id: UUID | None = None,
) -> list[dict]:
    items = list_uc.execute(ListDocumentsForReviewInput(
        only_extra=only_extra,
        group_id=group_id,
        employee_id=employee_id,
    ))
    return [_item_to_dict(it) for it in items]


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _flatten_groups(roots) -> dict:
    """Aplana el árbol de grupos (roots con children) a {id: group}."""
    flat: dict = {}

    def walk(groups) -> None:
        for g in groups:
            flat[g.id] = g
            if g.children:
                walk(g.children)

    walk(roots)
    return flat


def _group_path(group_id, flat) -> str:
    """Ruta 'Zona / Subgrupo' subiendo por parent_id."""
    names: list[str] = []
    seen: set = set()
    current = flat.get(group_id) if group_id else None
    while current and current.id not in seen:
        seen.add(current.id)
        names.append(current.name)
        current = flat.get(current.parent_id) if current.parent_id else None
    return " / ".join(reversed(names)) if names else "(sin grupo)"


# ---------------------------------------------------------------------------
# Página principal
# ---------------------------------------------------------------------------


@router.get("/reclassify", response_class=HTMLResponse)
async def reclassify_page(
    request: Request,
    only_extra: bool = False,
    group_id: str | None = None,
    employee_id: str | None = None,
    list_uc: ListDocumentsForReview = Depends(get_list_documents_for_review),
    document_type_repo: SupabaseDocumentTypeRepository = Depends(get_document_type_repo),
    groups_uc: ListGroups = Depends(get_list_groups),
):
    gid = _parse_uuid(group_id)
    eid = _parse_uuid(employee_id)
    items = _collect_items(list_uc, only_extra, gid, eid)

    # Opciones DESTINO del select "Reasignar a": solo tipos activos y SIN los
    # autogenerados de categoría EXTRA (cuyo name es el nombre del archivo), para
    # no ensuciar el catálogo. Esto NO afecta la lista de documentos pendientes
    # (esos sí incluyen los EXTRA).
    document_types = sorted(
        document_type_repo.list_active(exclude_category="EXTRA"),
        key=lambda dt: (dt.category, normalize_name_key(dt.name)),
    )

    return templates.TemplateResponse("documents/reclassify.html", {
        "request": request,
        "items": items,
        "document_types": document_types,        # activos, sin EXTRA, por categoría
        "zonas": groups_uc.execute(),            # grupos raíz (para el filtro)
        "only_extra": only_extra,
        "selected_group_id": group_id or "",
        "selected_employee_id": employee_id or "",
    })


# ---------------------------------------------------------------------------
# Lista JSON (recarga por filtros, sin refrescar la página)
# ---------------------------------------------------------------------------


@router.get("/reclassify/list")
async def reclassify_list(
    only_extra: bool = False,
    group_id: str | None = None,
    employee_id: str | None = None,
    list_uc: ListDocumentsForReview = Depends(get_list_documents_for_review),
):
    gid = _parse_uuid(group_id)
    eid = _parse_uuid(employee_id)
    return JSONResponse({"items": _collect_items(list_uc, only_extra, gid, eid)})


# ---------------------------------------------------------------------------
# Autocompletar de empleados (busca por nombre, activos e inactivos)
# ---------------------------------------------------------------------------


@router.get("/reclassify/search-employees")
async def search_employees(
    q: str = "",
    employee_repo: SupabaseEmployeeRepository = Depends(get_employee_repo),
    group_repo: SupabaseGroupRepository = Depends(get_group_repo),
):
    matches = employee_repo.search_by_name(q, limit=15)
    flat = _flatten_groups(group_repo.list_all())
    results = [
        {
            "id": str(e.id),
            "name": e.name,
            "group_path": _group_path(e.group_id, flat),
        }
        for e in matches
    ]
    return JSONResponse({"results": results})


# ---------------------------------------------------------------------------
# Aplicar recategorización
# ---------------------------------------------------------------------------


@router.post("/reclassify/{document_id}")
async def reclassify_apply(
    document_id: UUID,
    new_document_type_id: str = Form(...),
    resolve_conflict: str | None = Form(None),
    use_case: ReclassifyDocument = Depends(get_reclassify_document),
    document_repo: SupabaseDocumentRepository = Depends(get_document_repo),
    document_type_repo: SupabaseDocumentTypeRepository = Depends(get_document_type_repo),
):
    # Normaliza cadenas vacías provenientes del formulario a None.
    resolve = resolve_conflict or None

    # "EXTRA_AUTO": el usuario quiere marcar el documento como Extra. Se le crea
    # (o reutiliza) un tipo EXTRA propio derivado del nombre del archivo actual.
    try:
        if new_document_type_id == EXTRA_AUTO_SENTINEL:
            document = document_repo.get_by_id(document_id)
            if document is None:
                return JSONResponse(
                    {"ok": False, "error": "Documento no encontrado."}, status_code=404
                )
            target_type_id = get_or_create_extra_type(document_type_repo, document.file_name)
        else:
            target_type_id = UUID(new_document_type_id)
    except ValueError:
        return JSONResponse(
            {"ok": False, "error": "Tipo de documento no válido."}, status_code=400
        )

    try:
        result = use_case.execute(ReclassifyDocumentInput(
            document_id=document_id,
            new_document_type_id=target_type_id,
            resolve_conflict=resolve,
        ))
    except DomainError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    if result.status == STATUS_CONFLICT:
        return JSONResponse({
            "conflict": True,
            "existing_file_name": result.existing_file_name,
            "existing_document_type_name": result.existing_document_type_name,
        })

    # updated | cancelled → el frontend avanza al siguiente en ambos casos.
    return JSONResponse({"ok": True, "status": result.status})
