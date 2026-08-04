"""
reclasificar_sospechosos.py
===========================
Re-clasifica POR CONTENIDO VISUAL los documentos marcados como sospechosos en
conflictos_reporte.csv (generado por detectar_conflictos.py).

IMPORTANTE (diseño):
  Este script NO reimplementa la conversión de imagen ni la llamada a Ollama.
  Reutiliza el clasificador de producción `OllamaDocumentClassifier`
  (infrastructure/ollama/document_classifier.py): su `_resolve_image` /
  `_pdf_to_image`, su llamada a `/api/generate` (`_generate`) y su
  `_match_code`. La única diferencia intencional es el prompt: aquí se pide
  clasificar SOLO por el contenido visual, sin incluir el nombre del archivo.

Flujo:
  1. Lee conflictos_reporte.csv y extrae el drive_file_id de cada drive_url.
  2. Antes de procesar nada, hace una PRUEBA REAL de generación contra Ollama.
     Si Ollama no puede generar (p. ej. el motor llama-server está caído y
     /api/generate responde 500), se aborta con un mensaje claro en vez de
     marcar cientos de documentos como "revisión manual" ocultando el fallo.
  3. Para cada documento:
       - Descarga el archivo desde Google Drive.
       - Resuelve la imagen con la lógica de producción (PDF→PNG, imágenes).
       - Si no es visualizable (p. ej. .docx) → "requiere revisión manual".
       - Envía la imagen a Ollama (contenido únicamente). Si devuelve un tipo
         distinto y válido → se propone el cambio; si no clasifica → manual.
  4. Muestra TODOS los cambios propuestos (tipo actual → tipo nuevo) y pide
     confirmación: "¿Aplicar estos N cambios? (s/n):".
  5. Solo tras confirmar, actualiza document_type_id en la tabla documents.
  6. Escribe reclasificacion_log.csv con el resultado de cada caso.

No toca bulk_upload.py ni la lógica de migración.

Uso:
    python reclasificar_sospechosos.py
"""

from __future__ import annotations

import base64
import csv
import io
import os
import re
import sys

from dotenv import load_dotenv

load_dotenv()

from domain.entities.document_type import EXTRA_CATEGORY, DocumentType
from infrastructure.google_drive.drive_adapter import _build_service
from infrastructure.ollama.document_classifier import OllamaDocumentClassifier
from infrastructure.supabase.client import get_supabase_client
from infrastructure.supabase.document_type_repository import (
    SupabaseDocumentTypeRepository,
)

# ── Configuración ─────────────────────────────────────────────────────────
_INPUT_CSV = "conflictos_reporte.csv"
_LOG_CSV = "reclasificacion_log.csv"
_DRIVE_ID_RE = re.compile(r"/d/([A-Za-z0-9_-]+)")

# Resultados posibles por documento (para el log).
_R_UPDATED = "actualizado"
_R_UNCHANGED = "sin_cambio"
_R_MANUAL = "requiere_revision_manual"
_R_DOWNLOAD_ERR = "error_descarga"
_R_NOT_FOUND = "documento_no_encontrado_en_bd"
_R_CANCELLED = "cancelado"


# ── Prompt de clasificación por contenido (ignora el nombre del archivo) ───

def _build_content_prompt(catalog: list[DocumentType]) -> str:
    """Prompt que pide clasificar SOLO por la imagen, sin nombre de archivo."""
    catalog_str = "\n".join(
        f"- {dt.code}: {dt.name} ({dt.category})" for dt in catalog
    )
    return (
        "Eres un clasificador de documentos de recursos humanos de una empresa "
        "colombiana.\n\n"
        "Analiza ÚNICAMENTE el contenido visible en la imagen adjunta. "
        "NO dispones del nombre del archivo y no debes inventarlo.\n\n"
        "Categorías disponibles (código: descripción):\n"
        f"{catalog_str}\n\n"
        "Responde ÚNICAMENTE con el código exacto de la categoría que corresponde. "
        "Sin explicación, sin puntuación, sin comillas, sin texto adicional.\n"
        "Si el contenido no corresponde con ninguna categoría, responde exactamente: NINGUNA"
    )


def _classify_by_content(
    classifier: OllamaDocumentClassifier,
    image_bytes: bytes,
    prompt: str,
    by_code: dict[str, DocumentType],
) -> DocumentType | None:
    """
    Envía la imagen a Ollama reutilizando `_generate` y `_match_code` de
    producción. Devuelve el DocumentType detectado o None.
    """
    payload = {
        "model": classifier._model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
        "images": [base64.b64encode(image_bytes).decode("ascii")],
    }
    raw = classifier._generate(payload)  # None ante cualquier fallo/timeout
    if raw is None:
        return None
    return classifier._match_code(raw, by_code)


def _ollama_can_generate(classifier: OllamaDocumentClassifier) -> bool:
    """
    Prueba REAL de generación (texto, sin imagen). Distingue 'motor caído'
    de 'documento ambiguo': si esto falla, /api/generate no funciona y no
    tiene sentido procesar 200 documentos para marcarlos todos como manual.
    """
    raw = classifier._generate({
        "model": classifier._model,
        "prompt": "Responde con la palabra OK.",
        "stream": False,
        "options": {"temperature": 0},
    })
    return raw is not None


# ── Drive ─────────────────────────────────────────────────────────────────

def _drive_id_from_url(url: str) -> str | None:
    m = _DRIVE_ID_RE.search(url or "")
    return m.group(1) if m else None


def _download(drive, file_id: str) -> tuple[bytes | None, str]:
    """Devuelve (bytes, mime_type). bytes=None si falla la descarga."""
    from googleapiclient.http import MediaIoBaseDownload

    mime = ""
    try:
        meta = drive.files().get(
            fileId=file_id, fields="mimeType", supportsAllDrives=True
        ).execute()
        mime = meta.get("mimeType", "")
    except Exception:
        pass
    try:
        request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue(), mime
    except Exception:
        return None, mime


# ───────────────────────────────────────────────────────────────────────────


def _read_suspects() -> list[dict]:
    if not os.path.exists(_INPUT_CSV):
        print(f"✗ No se encontró {_INPUT_CSV}. Corre antes detectar_conflictos.py.")
        sys.exit(1)
    with open(_INPUT_CSV, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def run() -> None:
    db = get_supabase_client()
    drive = _build_service()

    type_repo = SupabaseDocumentTypeRepository(db)
    classifier = OllamaDocumentClassifier(type_repo)

    # ── Comprobaciones de Ollama (disponible Y capaz de generar) ──────────
    if not classifier.is_available():
        print(f"✗ Ollama no responde en {classifier._base_url}. "
              f"Arráncalo con 'ollama serve'.")
        sys.exit(1)
    if not _ollama_can_generate(classifier):
        print(
            "✗ Ollama responde pero NO puede generar (/api/generate falla).\n"
            "  Suele ser el motor de inferencia caído: 'llama-server binary not found'.\n"
            "  Reinstala/actualiza Ollama y verifica que el modelo "
            f"'{classifier._model}' esté descargado ('ollama run {classifier._model}').\n"
            "  Se aborta para no marcar todos los documentos como 'revisión manual'."
        )
        sys.exit(1)

    # Catálogo (sin EXTRA) reutilizando el repositorio de producción.
    catalog = type_repo.list_active(exclude_category=EXTRA_CATEGORY)
    by_code = {dt.code.upper(): dt for dt in catalog}
    prompt = _build_content_prompt(catalog)

    suspects = _read_suspects()
    seen_ids: set[str] = set()
    log_rows: list[dict] = []
    proposals: list[dict] = []

    print(f"Ollama OK. Analizando {len(suspects)} filas sospechosas...\n")

    for row in suspects:
        drive_url = row.get("drive_url", "")
        file_id = _drive_id_from_url(drive_url)
        file_name = row.get("nombre_archivo", "")

        if not file_id or file_id in seen_ids:
            continue
        seen_ids.add(file_id)

        # Localizar el documento en BD por su drive_file_id.
        doc_resp = (
            db.table("documents")
            .select("id, document_type_id, file_name")
            .eq("drive_file_id", file_id)
            .limit(1)
            .execute()
        )
        if not doc_resp.data:
            log_rows.append(_log(file_name, drive_url, "?", "?", _R_NOT_FOUND))
            continue
        doc = doc_resp.data[0]
        current = type_repo.get_by_id(doc["document_type_id"])
        actual_code = current.code if current else "?"

        # Descargar y resolver imagen con la lógica de producción.
        file_bytes, mime = _download(drive, file_id)
        if file_bytes is None:
            log_rows.append(_log(file_name, drive_url, actual_code, "-", _R_DOWNLOAD_ERR))
            print(f"  ⚠  {file_name}: no se pudo descargar")
            continue

        image_bytes = classifier._resolve_image(file_bytes, mime)
        if image_bytes is None:
            log_rows.append(_log(file_name, drive_url, actual_code, "-", _R_MANUAL))
            print(f"  ↷  {file_name}: no visualizable ({mime or 'sin mime'}) → revisión manual")
            continue

        detected = _classify_by_content(classifier, image_bytes, prompt, by_code)
        if detected is None:
            log_rows.append(_log(file_name, drive_url, actual_code, "-", _R_MANUAL))
            print(f"  ↷  {file_name}: Ollama no determinó el tipo → revisión manual")
            continue

        if detected.code.upper() == actual_code.upper():
            log_rows.append(_log(file_name, drive_url, actual_code, detected.code, _R_UNCHANGED))
            print(f"  =  {file_name}: se mantiene {actual_code}")
            continue

        proposals.append({
            "doc_id": doc["id"],
            "file_name": file_name,
            "drive_url": drive_url,
            "actual": actual_code,
            "nuevo": detected.code,
            "new_type_id": str(detected.id),
        })
        print(f"  →  {file_name}: {actual_code}  →  {detected.code}")

    # ── Confirmación ──────────────────────────────────────────────────────
    if not proposals:
        print("\nNo hay cambios que proponer.")
        _write_log(log_rows)
        return

    print(f"\n{'='*60}\nCambios propuestos ({len(proposals)}):")
    for p in proposals:
        print(f"  {p['file_name']:<45} {p['actual']}  →  {p['nuevo']}")

    answer = input(f"\n¿Aplicar estos {len(proposals)} cambios? (s/n): ").strip().lower()
    if answer != "s":
        print("Cancelado. No se aplicó ningún cambio.")
        for p in proposals:
            log_rows.append(
                _log(p["file_name"], p["drive_url"], p["actual"], p["nuevo"], _R_CANCELLED)
            )
        _write_log(log_rows)
        return

    # ── Aplicar ───────────────────────────────────────────────────────────
    applied = 0
    for p in proposals:
        try:
            db.table("documents").update(
                {"document_type_id": p["new_type_id"]}
            ).eq("id", p["doc_id"]).execute()
            applied += 1
            log_rows.append(
                _log(p["file_name"], p["drive_url"], p["actual"], p["nuevo"], _R_UPDATED)
            )
        except Exception as exc:
            log_rows.append(
                _log(p["file_name"], p["drive_url"], p["actual"], p["nuevo"],
                     f"error_actualizacion: {exc}")
            )

    _write_log(log_rows)
    print(f"\n✓ {applied}/{len(proposals)} documentos actualizados.")


def _log(file_name: str, drive_url: str, actual: str, nuevo: str, resultado: str) -> dict:
    return {
        "nombre_archivo": file_name,
        "drive_url": drive_url,
        "tipo_actual": actual,
        "tipo_propuesto": nuevo,
        "resultado": resultado,
    }


def _write_log(rows: list[dict]) -> None:
    fieldnames = ["nombre_archivo", "drive_url", "tipo_actual", "tipo_propuesto", "resultado"]
    with open(_LOG_CSV, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Log escrito en {_LOG_CSV} ({len(rows)} casos).")


if __name__ == "__main__":
    print("=" * 60)
    print("  Re-clasificación dirigida por contenido visual (Ollama)")
    print("=" * 60)
    run()
