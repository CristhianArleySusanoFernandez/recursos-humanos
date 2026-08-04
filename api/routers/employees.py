import unicodedata
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from api.dependencies import (
    get_create_employee,
    get_deactivate_employee,
    get_delete_employee,
    get_employee_checklist,
    get_group_repo,
    get_list_employees,
    get_list_groups,
    get_update_employee,
)
from api.templating import templates
from application.use_cases.create_employee import CreateEmployee, CreateEmployeeInput
from application.use_cases.deactivate_employee import DeactivateEmployee
from application.use_cases.delete_employee import DeleteEmployee
from application.use_cases.get_employee_checklist import GetEmployeeChecklist
from application.use_cases.list_employees import ListEmployees
from application.use_cases.list_groups import ListGroups
from application.use_cases.update_employee import UpdateEmployee, UpdateEmployeeInput
from domain.exceptions import DomainError, EmployeeNotFoundError
from domain.ports.group_repository import GroupRepository

router = APIRouter()

_RETIRADOS_ROOT_NAME = "RETIRADOS"


def _url_encode(text: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(text)


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().upper()


def _retirement_groups(group_repo: GroupRepository) -> list:
    """Subgrupos del grupo raíz cuyo nombre normalizado es RETIRADOS."""
    for root in group_repo.list_roots():
        if _normalize(root.name) == _RETIRADOS_ROOT_NAME:
            return group_repo.list_children(root.id)
    return []


# ---------------------------------------------------------------------------
# Panel principal — empleados activos
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def list_active(
    request: Request,
    list_uc: ListEmployees = Depends(get_list_employees),
    groups_uc: ListGroups = Depends(get_list_groups),
    error: str | None = None,
):
    employees = list_uc.execute(active_only=True)
    groups = groups_uc.execute()
    return templates.TemplateResponse("employees/list.html", {
        "request": request,
        "employees": employees,
        "groups": groups,
        "error": error,
    })


# ---------------------------------------------------------------------------
# Empleados inactivos
# ---------------------------------------------------------------------------


@router.get("/inactive", response_class=HTMLResponse)
async def list_inactive(
    request: Request,
    list_uc: ListEmployees = Depends(get_list_employees),
    groups_uc: ListGroups = Depends(get_list_groups),
    error: str | None = None,
):
    employees = list_uc.execute(active_only=False)
    groups = groups_uc.execute()
    return templates.TemplateResponse("employees/inactive.html", {
        "request": request,
        "employees": employees,
        "groups": groups,
        "error": error,
    })


# ---------------------------------------------------------------------------
# Crear empleado
# ---------------------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
async def new_employee_form(
    request: Request,
    groups_uc: ListGroups = Depends(get_list_groups),
    error: str | None = None,
):
    groups = groups_uc.execute()
    return templates.TemplateResponse("employees/form.html", {
        "request": request,
        "employee": None,
        "groups": groups,
        "error": error,
    })


@router.post("/new")
async def create_employee(
    request: Request,
    name: str = Form(...),
    position: str = Form(...),
    group_id: str = Form(...),
    use_case: CreateEmployee = Depends(get_create_employee),
    groups_uc: ListGroups = Depends(get_list_groups),
):
    try:
        use_case.execute(CreateEmployeeInput(
            name=name,
            position=position,
            group_id=UUID(group_id),
        ))
    except (DomainError, ValueError) as exc:
        groups = groups_uc.execute()
        return templates.TemplateResponse("employees/form.html", {
            "request": request,
            "employee": None,
            "groups": groups,
            "error": str(exc),
        }, status_code=422)
    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------------------------
# Detalle / checklist
# ---------------------------------------------------------------------------


@router.get("/{employee_id}", response_class=HTMLResponse)
async def employee_detail(
    request: Request,
    employee_id: UUID,
    use_case: GetEmployeeChecklist = Depends(get_employee_checklist),
    groups_uc: ListGroups = Depends(get_list_groups),
    group_repo: GroupRepository = Depends(get_group_repo),
    error: str | None = None,
):
    groups = groups_uc.execute()
    retirement_groups = _retirement_groups(group_repo)
    try:
        checklist = use_case.execute(employee_id)
    except EmployeeNotFoundError as exc:
        return templates.TemplateResponse("employees/detail.html", {
            "request": request,
            "checklist": None,
            "groups": groups,
            "retirement_groups": retirement_groups,
            "error": str(exc),
        }, status_code=404)
    return templates.TemplateResponse("employees/detail.html", {
        "request": request,
        "checklist": checklist,
        "groups": groups,
        "retirement_groups": retirement_groups,
        "error": error,
    })


# ---------------------------------------------------------------------------
# Editar empleado
# ---------------------------------------------------------------------------


@router.post("/{employee_id}/edit")
async def edit_employee(
    request: Request,
    employee_id: UUID,
    name: str = Form(...),
    position: str = Form(...),
    group_id: str = Form(...),
    use_case: UpdateEmployee = Depends(get_update_employee),
    checklist_uc: GetEmployeeChecklist = Depends(get_employee_checklist),
    groups_uc: ListGroups = Depends(get_list_groups),
):
    try:
        use_case.execute(UpdateEmployeeInput(
            employee_id=employee_id,
            name=name,
            position=position,
            group_id=UUID(group_id),
        ))
    except (DomainError, ValueError) as exc:
        try:
            checklist = checklist_uc.execute(employee_id)
        except DomainError:
            checklist = None
        groups = groups_uc.execute()
        return templates.TemplateResponse("employees/detail.html", {
            "request": request,
            "checklist": checklist,
            "groups": groups,
            "error": str(exc),
        }, status_code=422)
    return RedirectResponse(url=f"/{employee_id}", status_code=303)


# ---------------------------------------------------------------------------
# Desactivar / reactivar
# ---------------------------------------------------------------------------


@router.post("/{employee_id}/deactivate")
async def deactivate_employee(
    employee_id: UUID,
    retirement_group_id: UUID = Form(...),
    use_case: DeactivateEmployee = Depends(get_deactivate_employee),
):
    try:
        use_case.execute(employee_id, retirement_group_id)
    except DomainError as exc:
        return RedirectResponse(
            url=f"/{employee_id}?error={_url_encode(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(url="/", status_code=303)


@router.post("/{employee_id}/delete")
async def delete_employee(
    employee_id: UUID,
    use_case: DeleteEmployee = Depends(get_delete_employee),
):
    try:
        use_case.execute(employee_id)
    except DomainError as exc:
        return RedirectResponse(
            url=f"/inactive?error={_url_encode(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(url="/inactive", status_code=303)


@router.post("/{employee_id}/reactivate")
async def reactivate_employee(
    employee_id: UUID,
    use_case: UpdateEmployee = Depends(get_update_employee),
):
    try:
        use_case.execute(UpdateEmployeeInput(employee_id=employee_id, is_active=True))
    except DomainError:
        pass
    return RedirectResponse(url=f"/{employee_id}", status_code=303)
