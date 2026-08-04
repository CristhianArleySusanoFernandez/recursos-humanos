from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from api.dependencies import (
    get_create_group,
    get_delete_group,
    get_list_groups,
    get_update_group,
)
from api.templating import templates
from application.use_cases.create_group import CreateGroup, CreateGroupInput
from application.use_cases.delete_group import DeleteGroup
from application.use_cases.list_groups import ListGroups
from application.use_cases.update_group import UpdateGroup, UpdateGroupInput
from domain.exceptions import DomainError

router = APIRouter(prefix="/groups")


def _url_encode(text: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(text)


# ---------------------------------------------------------------------------
# Lista de grupos
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def list_groups(
    request: Request,
    use_case: ListGroups = Depends(get_list_groups),
    error: str | None = None,
):
    groups = use_case.execute()
    return templates.TemplateResponse("groups/list.html", {
        "request": request,
        "groups": groups,
        "error": error,
    })


# ---------------------------------------------------------------------------
# Crear grupo
# ---------------------------------------------------------------------------


@router.post("")
async def create_group(
    request: Request,
    name: str = Form(...),
    parent_id: str = Form(""),
    use_case: CreateGroup = Depends(get_create_group),
    list_uc: ListGroups = Depends(get_list_groups),
):
    parent_uuid = UUID(parent_id) if parent_id.strip() else None
    try:
        use_case.execute(CreateGroupInput(name=name, parent_id=parent_uuid))
    except (DomainError, ValueError) as exc:
        groups = list_uc.execute()
        return templates.TemplateResponse("groups/list.html", {
            "request": request,
            "groups": groups,
            "error": str(exc),
        }, status_code=422)
    return RedirectResponse(url="/groups", status_code=303)


# ---------------------------------------------------------------------------
# Editar grupo
# ---------------------------------------------------------------------------


@router.post("/{group_id}/edit")
async def edit_group(
    group_id: UUID,
    name: str = Form(...),
    use_case: UpdateGroup = Depends(get_update_group),
):
    try:
        use_case.execute(UpdateGroupInput(group_id=group_id, name=name))
    except DomainError as exc:
        return RedirectResponse(
            url=f"/groups?error={_url_encode(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(url="/groups", status_code=303)


# ---------------------------------------------------------------------------
# Eliminar grupo
# ---------------------------------------------------------------------------


@router.post("/{group_id}/delete")
async def delete_group(
    group_id: UUID,
    use_case: DeleteGroup = Depends(get_delete_group),
):
    try:
        use_case.execute(group_id)
    except DomainError as exc:
        return RedirectResponse(
            url=f"/groups?error={_url_encode(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(url="/groups", status_code=303)
