from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # Carga .env antes de que cualquier adaptador lea variables de entorno.

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.auth import verify_credentials
from api.routers import document_types, documents, employees, groups, reclassify
from api.templating import templates
from domain.exceptions import DomainError


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="RRHH – Checklist Documental",
    description="Gestión de documentos de empleados con Google Drive.",
    lifespan=lifespan,
    # Dependencia GLOBAL: HTTP Basic Auth aplicada a TODAS las rutas de TODOS los
    # routers (empleados, documentos, grupos, tipos de documento, recategorizar).
    # Ninguna ruta queda sin proteger.
    dependencies=[Depends(verify_credentials)],
)

app.mount("/static", StaticFiles(directory="api/static"), name="static")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
# Orden de registro importa: FastAPI evalúa rutas en orden.
# groups y document_types van PRIMERO porque tienen rutas estáticas (/groups,
# /document-types) que de lo contrario serían capturadas por el patrón
# dinámico /{employee_id} del router de employees.
# documents va después de employees porque sus rutas ya llevan /{employee_id}/...

app.include_router(groups.router)
app.include_router(document_types.router)
app.include_router(reclassify.router)  # /reclassify: estática, antes que /{employee_id}
app.include_router(employees.router)
app.include_router(documents.router)


# ---------------------------------------------------------------------------
# Manejadores globales de error
# ---------------------------------------------------------------------------


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> HTMLResponse:
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": str(exc)},
        status_code=400,
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> HTMLResponse:
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": "Página no encontrada."},
        status_code=404,
    )
