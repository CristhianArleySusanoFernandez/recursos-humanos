"""
migrate_drive.py
================
Migración masiva de empleados y documentos desde Google Drive a Supabase.

Lee la estructura de la carpeta PERSONAL original (GOOGLE_DRIVE_SOURCE_FOLDER_ID),
crea los empleados en Supabase y registra sus documentos, clasificándolos con:
    Nivel 1  → palabras clave sobre el nombre del archivo.
    Nivel 2  → palabras clave de descarte → EXTRA.
    Nivel 3  → Ollama local (gemma3:4b). Para PDFs se rasteriza la primera
               página a PNG con PyMuPDF antes de enviarla al modelo.

Los archivos NUNCA se mueven ni se eliminan de Drive: solo se leen y se
registra su referencia (drive_file_id) en Supabase.

Estructura esperada en el origen:
    PERSONAL/
        TUNJA/
            ASESORES/
                JUAN PEREZ/
                    CONTRATO_0001.pdf
        RETIRADOS/
            ...

Uso:
    python migrate_drive.py           # migración completa
    python migrate_drive.py --test    # solo el primer empleado encontrado
"""

from __future__ import annotations

import base64
import csv
import io
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import hashlib

import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Importar infraestructura del proyecto
# ---------------------------------------------------------------------------
from infrastructure.google_drive.drive_adapter import _build_service
from infrastructure.supabase.client import get_supabase_client

# ---------------------------------------------------------------------------
# Configuración de Ollama (idéntica a infrastructure/ollama/document_classifier.py)
# ---------------------------------------------------------------------------
_OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
_OLLAMA_TIMEOUT = 60.0
_PDF_RENDER_DPI = 150

# Zonas que se procesan (comparadas ya normalizadas). ESTUDIANTES se excluye.
ZONAS_VALIDAS: set[str] = {"TUNJA", "BARBOSA", "CHIQUINQUIRA", "RETIRADOS"}

_FOLDER_MIME = "application/vnd.google-apps.folder"
_PDF_MIME = "application/pdf"
_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_VIEW_URL = "https://drive.google.com/file/d/{}/view"

# Categoría especial para documentos que no encajan en el checklist.
EXTRA_CATEGORY = "EXTRA"

# ---------------------------------------------------------------------------
# Constantes de clasificación por nombre (Nivel 1 y Nivel 2)
# ---------------------------------------------------------------------------

# Nivel 1: palabras clave → código de tipo de documento.
# El orden importa: se evalúan de arriba a abajo, primera coincidencia gana.
KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["HOJA DE VIDA INTERNA"],              "HOJA_DE_VIDA_INTERNA"),
    (["HOJA DE VIDA", "HV "],               "HOJA_DE_VIDA"),
    (["AUTOBIO"],                            "AUTOBIOGRAFIA"),
    (["CONTRATO", "OTRO SI", "OTRO_SI",
      "OTROSÍ", "OTROSI"],                  "CONTRATO"),
    (["CEDULA", "C.C.", "-C.PDF"],           "FOTOCOPIA_CEDULA"),
    (["RUT_LICENCIA", "LICENCIA DE CONDUCCION",
      "LICENCIA DE CONDUCCIÓN"],             "RUT_LICENCIA"),
    (["RUT"],                                "RUT"),
    (["ANTECEDENTES", "CONTRALORIA",
      "CONTRALORÍA", "PROCURADURIA",
      "PROCURADURÍA", "PONAL"],             "ANTECEDENTES"),
    (["COMFABOY", "COMFA"],                  "AFILIACION_COMFABOY"),
    (["AFILIACION", "FORMULARIO DE AFILIACION"], "AFILIACION_EPS"),
    (["EPS", "COOSALUD", "SALUD"],           "AFILIACION_EPS"),
    (["ARL"],                                "AFILIACION_ARL"),
    (["PENSION", "PENSIÓN"],                 "CERT_PENSION_EPS"),
    (["BANCARI", "BANCO", "CUENTA BANCO"],   "CERT_BANCARIA"),
    (["MANIPULACION", "MANIPULACIÓN"],       "CERT_MANIPULACION"),
    (["INDUCCION", "INDUCCIÓN"],             "INDUCCION_SG_SST"),
    (["LLAMADO"],                            "LLAMADO_REFLEXION"),
    (["HABEAS"],                             "HABEAS_DATA"),
    (["ENTREVISTA DE RETIRO"],               "ENTREVISTA_RETIRO"),
    (["ENTREVISTA"],                         "FORMATO_ENTREVISTA"),
    (["REGISTRO CIVIL", "TARJETA"],          "REGISTRO_CIVIL"),
    (["CONYUGUE", "CONYUGE", "CÓNYUGE"],     "CEDULA_CONYUGE"),
    (["CERTIFICADO DE ESTUDIO",
      "CERTIFICACION ESTUDIO",
      "CERTIFICACIÓN ESTUDIO"],             "CERTIFICADO_ESTUDIO"),
    (["CERTIFICADO LABORAL",
      "CERTIFICACION LABORAL",
      "CERTIFICACIÓN LABORAL"],             "CERTIFICADO_LABORAL"),
    (["CARTA DE RETIRO"],                    "CARTA_RETIRO"),
    (["RETIRO ARL"],                         "RETIRO_ARL"),
    (["CESANTIA", "CESANTÍAS"],              "CARTA_RETIRO_CESANTIAS"),
    (["LIQUIDACION", "LIQUIDACIÓN"],         "LIQUIDACION"),
    (["EXAMEN DE EGRESO", "ORDEN EXAMEN"],   "ORDEN_EXAMEN_EGRESO"),
    (["CERTIFICADO APORTES",
      "CERT APORTES"],                      "CERT_APORTES"),
]

# Nivel 2: si el nombre contiene alguna de estas palabras → EXTRA (sin llamada a IA).
EXTRA_KEYWORDS: list[str] = [
    "DOTACION", "DOTACIÓN", "VACACIONES", "VACCIONES", "PERMISO",
    "HORARIO", "NOMINA", "NÓMINA", "COMPROBANTE", "SOLICITUD",
    "CAMBIO DE CARGO", "DIA DE LA FAMILIA", "REGLAMENTO", "ACTIVIDADES",
    "CARGUES", "RECOMENDACIONES", "GMAIL", "WHATSAPP", "NOTIFICACION",
    "NOTIFICACIÓN", "FORMATO", "ENTREGA", "ADRES", "RUAF", "SIMIT",
    "RAYOGAS", "PAGO",
]


# ---------------------------------------------------------------------------
# Normalización de texto (idéntica a sync_structure.py: Ñ se conserva)
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """MAYÚSCULAS, sin tildes, sin espacios sobrantes. La Ñ se conserva."""
    protected = text.replace("ñ", "\0").replace("Ñ", "\0")
    nfkd = unicodedata.normalize("NFKD", protected)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.replace("\0", "Ñ").strip().upper()


def _strip_retirados_prefix(name: str) -> str:
    """Quita el prefijo "RETIRADOS" de una subcategoría ya normalizada.

    "RETIRADOS BARBOSA" → "BARBOSA", "RETIRADOS_TUNJA" → "TUNJA",
    "RETIRADOSCHIQUINQUIRA" → "CHIQUINQUIRA". Si tras quitarlo queda vacío
    (la carpeta se llama solo "RETIRADOS"), se devuelve el nombre original.
    """
    for prefix in ("RETIRADOS_", "RETIRADOS ", "RETIRADOS"):
        if name.startswith(prefix):
            cleaned = name[len(prefix):].lstrip("_ ").strip()
            return cleaned or name
    return name


# ---------------------------------------------------------------------------
# Clasificación por nombre (Nivel 1 y Nivel 2)
# ---------------------------------------------------------------------------

def _keyword_matches(keyword: str, filename_upper: str) -> bool:
    """True si `keyword` aparece en `filename_upper` como token delimitado.

    Evita falsos positivos por substring: "ARL" ya no coincide dentro de
    "MARLEN" ni "RUT" dentro de "RUTA". Se considera coincidencia solo si la
    palabra clave está delimitada por inicio/fin, espacio, '_', '-', '.', o
    paréntesis (es decir, sin una letra A-Z/Ñ pegada a los lados).
    """
    pattern = r"(?<![A-ZÑ])" + re.escape(keyword) + r"(?![A-ZÑ])"
    return bool(re.search(pattern, filename_upper))


def classify_by_name(filename: str) -> str | None:
    """Nivel 1: clasifica por palabras clave. Retorna código o None."""
    upper = _normalize(filename)
    for keywords, code in KEYWORD_RULES:
        for kw in keywords:
            if _keyword_matches(_normalize(kw), upper):
                return code
    return None


def is_extra_by_name(filename: str) -> bool:
    """Nivel 2: descarta por palabras clave de descarte."""
    upper = _normalize(filename)
    return any(_keyword_matches(_normalize(kw), upper) for kw in EXTRA_KEYWORDS)


# ---------------------------------------------------------------------------
# Nivel 3: clasificación con Ollama (gemma3:4b)
# ---------------------------------------------------------------------------

def _pdf_to_image(file_bytes: bytes) -> bytes | None:
    """
    Rasteriza la primera página del PDF a PNG a 150 DPI con PyMuPDF.
    Retorna None si el PDF está corrupto, cifrado o vacío.
    """
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            if doc.page_count == 0:
                return None
            page = doc.load_page(0)
            pixmap = page.get_pixmap(dpi=_PDF_RENDER_DPI)
            return pixmap.tobytes("png")
    except Exception:
        return None


def _resolve_image(file_bytes: bytes, mime_type: str) -> bytes | None:
    """Bytes de imagen para el modelo, o None si no es visualizable."""
    mime = (mime_type or "").lower()
    if mime in _IMAGE_MIME_TYPES:
        return file_bytes
    if mime == _PDF_MIME:
        return _pdf_to_image(file_bytes)
    return None


def classify_with_ollama(
    filename: str,
    file_bytes: bytes | None,
    mime_type: str,
    catalog: list[dict],
) -> str | None:
    """
    Nivel 3: pregunta a Ollama a qué código corresponde el archivo.
    `catalog` es la lista de tipos válidos (dicts con code, name, category),
    excluyendo la categoría EXTRA.
    Retorna un código válido o None si el modelo no acierta / no responde.
    """
    by_code = {dt["code"].upper(): dt for dt in catalog}

    image_bytes = None
    if file_bytes is not None:
        image_bytes = _resolve_image(file_bytes, mime_type)
    use_vision = image_bytes is not None

    catalog_str = "\n".join(
        f"- {dt['code']}: {dt['name']} ({dt['category']})" for dt in catalog
    )
    source = (
        "Analiza el contenido de la imagen adjunta y el nombre del archivo."
        if use_vision
        else "Analiza ÚNICAMENTE el nombre del archivo (el contenido no está disponible)."
    )
    prompt = (
        "Eres un clasificador de documentos de recursos humanos de una empresa "
        "colombiana.\n\n"
        f"{source}\n\n"
        f"Nombre del archivo: {filename}\n\n"
        "Categorías disponibles (código: descripción):\n"
        f"{catalog_str}\n\n"
        "Responde ÚNICAMENTE con el código exacto de la categoría que corresponde. "
        "Sin explicación, sin puntuación, sin comillas, sin texto adicional.\n"
        "Si el archivo no corresponde con ninguna categoría, responde exactamente: NINGUNA"
    )

    payload: dict = {
        "model": _OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }
    if image_bytes is not None:
        payload["images"] = [base64.b64encode(image_bytes).decode("ascii")]

    try:
        with httpx.Client(timeout=_OLLAMA_TIMEOUT) as client:
            response = client.post(f"{_OLLAMA_BASE_URL}/api/generate", json=payload)
        if response.status_code != 200:
            return None
        raw = (response.json().get("response") or "").strip()
    except Exception:
        return None

    cleaned = raw.strip().strip("`\"'.,:;").upper()
    if cleaned in by_code:
        return by_code[cleaned]["code"]
    # El modelo a veces devuelve una frase; se prioriza el código más largo
    # para evitar falsos positivos (ej: "RUT" dentro de "RUT_LICENCIA").
    for code in sorted(by_code, key=len, reverse=True):
        if code in cleaned:
            return by_code[code]["code"]
    return None


def ollama_available() -> bool:
    """True si Ollama responde en /api/tags. Nunca lanza."""
    try:
        with httpx.Client(timeout=3.0) as client:
            return client.get(f"{_OLLAMA_BASE_URL}/api/tags").status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Registro de resultados
# ---------------------------------------------------------------------------

@dataclass
class ReportRow:
    empleado: str
    zona: str
    categoria: str
    archivo: str
    clasificacion: str
    metodo: str
    drive_file_id: str
    error: str = ""


# ---------------------------------------------------------------------------
# Lógica principal de migración
# ---------------------------------------------------------------------------

class Migrator:
    def __init__(self, test_mode: bool = False) -> None:
        self.test_mode = test_mode
        self.db = get_supabase_client()
        self.drive = _build_service()
        self.source_folder_id = os.environ.get("GOOGLE_DRIVE_SOURCE_FOLDER_ID", "")
        self.report: list[ReportRow] = []
        self._stop = False  # se activa en --test tras el primer empleado

        # Índice de grupos por (nombre_normalizado, parent_id). Es CLAVE que la
        # resolución de subgrupo sea relativa al padre (la zona): varias zonas
        # tienen subgrupos con el mismo nombre (Tunja/Asesores, Barbosa/Asesores,
        # …), así que un índice plano por nombre haría que "Asesores" de Barbosa
        # resolviera al "Asesores" de otra zona (el primero encontrado).
        self._groups_by_key: dict[tuple[str, str | None], dict] = {}
        # Zonas (grupos raíz, parent_id NULL) indexadas por nombre normalizado.
        self._roots_by_name: dict[str, dict] = {}
        self._doc_types: dict[str, dict] = {}  # code → row (id, code, name, category)
        self._extra_cache: dict[str, dict] = {}  # code EXTRA_* → row creado
        self._load_groups()
        self._load_doc_types()

    # ------------------------------------------------------------------
    # Carga inicial
    # ------------------------------------------------------------------

    def _load_groups(self) -> None:
        resp = self.db.table("groups").select("id, name, parent_id").execute()
        for row in (resp.data or []):
            key = (_normalize(row["name"]), row.get("parent_id"))
            self._groups_by_key[key] = row
            if row.get("parent_id") is None:
                self._roots_by_name[_normalize(row["name"])] = row
        print(f"  Grupos cargados desde Supabase: {len(self._groups_by_key)}")

    def _load_doc_types(self) -> None:
        resp = (
            self.db.table("document_types")
            .select("id, code, name, category")
            .execute()
        )
        for row in (resp.data or []):
            self._doc_types[row["code"].upper()] = row
        print(f"  Tipos de documento cargados: {len(self._doc_types)}")

    def _catalog_for_ai(self) -> list[dict]:
        """Tipos válidos para el prompt de Ollama, excluyendo EXTRA."""
        return [
            dt for dt in self._doc_types.values()
            if dt.get("category") != EXTRA_CATEGORY
        ]

    # ------------------------------------------------------------------
    # Comprobaciones previas
    # ------------------------------------------------------------------

    def preflight(self) -> None:
        """Valida entorno, Ollama y grupos antes de tocar nada."""
        problems: list[str] = []

        # Variables de entorno necesarias.
        for var in ("SUPABASE_URL", "SUPABASE_KEY", "GOOGLE_DRIVE_SOURCE_FOLDER_ID"):
            if not os.environ.get(var):
                problems.append(f"Falta la variable de entorno {var}")

        # Ollama corriendo.
        if not ollama_available():
            problems.append(
                f"Ollama no responde en {_OLLAMA_BASE_URL}. "
                f"Arráncalo con 'ollama serve' y verifica el modelo {_OLLAMA_MODEL}."
            )

        # Grupos poblados.
        if not self._groups_by_key:
            problems.append(
                "La tabla groups está vacía. Corre primero sync_structure.py."
            )

        if problems:
            print("\n✗ No se puede iniciar la migración:")
            for p in problems:
                print(f"    - {p}")
            sys.exit(1)

        print("  ✓ Ollama disponible")
        print("  ✓ Variables de entorno presentes")
        print(f"  ✓ Grupos poblados ({len(self._groups_by_key)})")

    # ------------------------------------------------------------------
    # Utilidades de Drive
    # ------------------------------------------------------------------

    def _list_folders(self, parent_id: str) -> list[dict]:
        return self._list(parent_id, only_folders=True)

    def _list_files(self, parent_id: str) -> list[dict]:
        return self._list(parent_id, only_folders=False)

    def _list(self, parent_id: str, only_folders: bool) -> list[dict]:
        op = "=" if only_folders else "!="
        results: list[dict] = []
        page_token = None
        while True:
            kwargs = dict(
                q=(
                    f"'{parent_id}' in parents "
                    f"and mimeType{op}'{_FOLDER_MIME}' "
                    f"and trashed=false"
                ),
                fields="nextPageToken, files(id, name, mimeType)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=1000,
            )
            if page_token:
                kwargs["pageToken"] = page_token
            resp = self.drive.files().list(**kwargs).execute()
            results.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return results

    def _download_file(self, file_id: str) -> bytes | None:
        """Descarga el archivo completo desde Drive (para clasificación con IA)."""
        try:
            from googleapiclient.http import MediaIoBaseDownload

            request = self.drive.files().get_media(
                fileId=file_id, supportsAllDrives=True
            )
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = dl.next_chunk()
            return buf.getvalue()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Supabase: empleados
    # ------------------------------------------------------------------

    def _find_employee(self, name: str, group_id: str) -> dict | None:
        resp = (
            self.db.table("employees")
            .select("id, name")
            .eq("name", name)
            .eq("group_id", group_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def _create_employee(self, name: str, group_id: str, is_active: bool) -> dict:
        row = {
            "id": str(uuid4()),
            "name": name,
            "position": "Por asignar",
            "group_id": group_id,
            "is_active": is_active,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.table("employees").insert(row).execute()
        return row

    # ------------------------------------------------------------------
    # Supabase: tipos y documentos
    # ------------------------------------------------------------------

    def _get_or_create_extra_type(self, filename: str) -> dict:
        """
        Crea (o reutiliza) un tipo EXTRA único por archivo, con category='EXTRA'.
        code = 'EXTRA_<md5[:8]>' evita chocar con UNIQUE(employee_id, document_type_id)
        y permite varios extras por empleado.
        """
        code = f"EXTRA_{hashlib.md5(filename.encode()).hexdigest()[:8].upper()}"

        if code in self._extra_cache:
            return self._extra_cache[code]
        if code in self._doc_types:
            self._extra_cache[code] = self._doc_types[code]
            return self._doc_types[code]

        row = {
            "id": str(uuid4()),
            "name": filename[:100],
            "code": code,
            "category": EXTRA_CATEGORY,
            "is_active": True,
            "order_index": 99,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.table("document_types").insert(row).execute()
        self._doc_types[code] = row
        self._extra_cache[code] = row
        return row

    def _doc_exists(self, employee_id: str, doc_type_id: str) -> bool:
        resp = (
            self.db.table("documents")
            .select("id")
            .eq("employee_id", employee_id)
            .eq("document_type_id", doc_type_id)
            .limit(1)
            .execute()
        )
        return bool(resp.data)

    def _save_document(
        self, employee_id: str, doc_type_id: str, file_name: str, drive_file_id: str
    ) -> None:
        row = {
            "id": str(uuid4()),
            "employee_id": employee_id,
            "document_type_id": doc_type_id,
            "file_name": file_name,
            "drive_file_id": drive_file_id,
            "drive_url": _VIEW_URL.format(drive_file_id),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.table("documents").insert(row).execute()

    # ------------------------------------------------------------------
    # Procesamiento de un archivo
    # ------------------------------------------------------------------

    def _process_file(
        self, file: dict, employee_id: str, zona: str, categoria: str, emp_name: str
    ) -> None:
        fname = file["name"]
        fid = file["id"]
        mime = file.get("mimeType", "")
        row = ReportRow(
            empleado=emp_name, zona=zona, categoria=categoria,
            archivo=fname, clasificacion="", metodo="", drive_file_id=fid,
        )

        try:
            code = classify_by_name(fname)
            if code:
                row.metodo, row.clasificacion = "nombre", code
                print(f"    ✓ {fname} → {code} (nombre)")
            elif is_extra_by_name(fname):
                row.metodo, row.clasificacion = "descarte", "EXTRA"
                print(f"    → EXTRA (descarte): {fname}")
            else:
                # Nivel 3: Ollama, con la primera página del PDF como imagen.
                content = self._download_file(fid)
                ai_code = classify_with_ollama(
                    fname, content, mime, self._catalog_for_ai()
                )
                if ai_code:
                    row.metodo, row.clasificacion = "ollama", ai_code
                    print(f"    ~ Ollama: {fname} → {ai_code}")
                else:
                    row.metodo, row.clasificacion = "ollama", "EXTRA"
                    print(f"    ~ Ollama: {fname} → EXTRA (sin match)")

            # Resolver el tipo de documento a registrar.
            if row.clasificacion == "EXTRA":
                dt = self._get_or_create_extra_type(fname)
            else:
                dt = self._doc_types.get(row.clasificacion)
                if dt is None:
                    dt = self._get_or_create_extra_type(fname)
                    row.clasificacion = "EXTRA (tipo no existía)"

            if self._doc_exists(employee_id, dt["id"]):
                print(f"      (ya existe, omitido)")
                row.error = "ya_existe"
                self.report.append(row)
                return

            self._save_document(employee_id, dt["id"], fname, fid)

        except Exception as exc:
            row.error = str(exc)
            print(f"    ✗ Error en {fname}: {exc}")

        self.report.append(row)

    # ------------------------------------------------------------------
    # Procesamiento de un empleado
    # ------------------------------------------------------------------

    def _process_employee_folder(
        self, folder: dict, group_row: dict, zona_name: str,
        categoria_name: str, is_active: bool,
    ) -> None:
        emp_name = folder["name"]
        folder_id = folder["id"]

        try:
            existing = self._find_employee(emp_name, group_row["id"])
            if existing:
                employee_id = existing["id"]
                print(f"  (ya existe) {emp_name}")
            else:
                created = self._create_employee(emp_name, group_row["id"], is_active)
                employee_id = created["id"]
                print(f"  ✓ Empleado creado: {emp_name} ({zona_name}/{categoria_name})")

            for f in self._list_files(folder_id):
                self._process_file(f, employee_id, zona_name, categoria_name, emp_name)

        except Exception as exc:
            print(f"  ✗ Error procesando empleado '{emp_name}': {exc}")
            self.report.append(ReportRow(
                empleado=emp_name, zona=zona_name, categoria=categoria_name,
                archivo="", clasificacion="", metodo="", drive_file_id="",
                error=str(exc),
            ))

        # En modo test, detenerse tras el primer empleado.
        if self.test_mode:
            self._stop = True

    # ------------------------------------------------------------------
    # Procesamiento de una categoría (subgrupo)
    # ------------------------------------------------------------------

    def _process_category_folder(
        self, folder: dict, zona_name: str, is_active: bool
    ) -> None:
        cat_name = _normalize(folder["name"])
        # Dentro de RETIRADOS las subcarpetas vienen con el prefijo "RETIRADOS"
        # (p. ej. "RETIRADOS BARBOSA"). En Supabase el subgrupo se llama solo
        # "BARBOSA", así que quitamos ese prefijo antes de buscar el match.
        if zona_name == "RETIRADOS":
            cat_name = _strip_retirados_prefix(cat_name)

        # La búsqueda del subgrupo SIEMPRE es relativa a la zona (padre) actual,
        # nunca global: primero resolvemos el grupo raíz de la zona y luego el
        # subgrupo por (nombre, parent_id=zona). Así "Asesores" de Barbosa jamás
        # puede resolver al "Asesores" de Tunja.
        zona_group = self._roots_by_name.get(zona_name)
        if zona_group is None:
            print(f"  ⚠  Zona raíz '{zona_name}' no encontrada en Supabase — omitida")
            return

        group_row = self._groups_by_key.get((cat_name, zona_group["id"]))
        if group_row is None:
            print(
                f"  ⚠  Subgrupo '{cat_name}' dentro de '{zona_name}' "
                f"no encontrado en Supabase — omitido"
            )
            return

        print(f"\n  Categoría: {cat_name}")
        for emp_folder in self._list_folders(folder["id"]):
            if self._stop:
                return
            self._process_employee_folder(
                emp_folder, group_row, zona_name, cat_name, is_active
            )

    # ------------------------------------------------------------------
    # Procesamiento de una zona (grupo raíz)
    # ------------------------------------------------------------------

    def _process_zona_folder(self, folder: dict) -> None:
        zona_name = _normalize(folder["name"])
        is_active = zona_name != "RETIRADOS"

        print(f"\n{'='*60}")
        print(f"Zona: {zona_name}  ({'activos' if is_active else 'inactivos'})")
        print(f"{'='*60}")

        for cat_folder in self._list_folders(folder["id"]):
            if self._stop:
                return
            self._process_category_folder(cat_folder, zona_name, is_active)

    # ------------------------------------------------------------------
    # Punto de entrada
    # ------------------------------------------------------------------

    def run(self) -> None:
        print("\nComprobaciones previas:")
        self.preflight()

        if self.test_mode:
            print("\n⚑ MODO TEST: solo se procesará el primer empleado encontrado.")

        print(f"\nCarpeta origen (PERSONAL): {self.source_folder_id}")
        zona_folders = self._list_folders(self.source_folder_id)
        if not zona_folders:
            print("✗ No se encontraron carpetas de zona en el origen.")
            sys.exit(1)

        print(f"Zonas encontradas: {[_normalize(f['name']) for f in zona_folders]}")

        # Procesar solo las zonas de la lista blanca (ESTUDIANTES queda fuera).
        zonas = [z for z in zona_folders if _normalize(z["name"]) in ZONAS_VALIDAS]
        print(f"Zonas a procesar:  {[_normalize(z['name']) for z in zonas]}\n")

        for zona in zonas:
            if self._stop:
                break
            self._process_zona_folder(zona)

        self._write_report()
        print(f"\n✓ Migración completada. Reporte: migracion_reporte.csv")
        print(f"  Filas en reporte: {len(self.report)}")
        errores = sum(1 for r in self.report if r.error and r.error != "ya_existe")
        print(f"  Errores: {errores}")

    # ------------------------------------------------------------------
    # Reporte CSV
    # ------------------------------------------------------------------

    def _write_report(self) -> None:
        with open("migracion_reporte.csv", "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "empleado", "zona", "categoria", "archivo",
                "clasificacion", "metodo", "drive_file_id", "error",
            ])
            writer.writeheader()
            for row in self.report:
                writer.writerow(row.__dict__)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_mode = "--test" in sys.argv[1:]

    print("=" * 60)
    print("  Migración masiva Drive → Supabase")
    print("  Distribuciones SantiagoDeTunja S.A.S.")
    if test_mode:
        print("  (modo test: solo el primer empleado)")
    print("=" * 60)

    confirm = input("\n¿Confirmas la migración? (s/n): ").strip().lower()
    if confirm != "s":
        print("Migración cancelada.")
        sys.exit(0)

    Migrator(test_mode=test_mode).run()
