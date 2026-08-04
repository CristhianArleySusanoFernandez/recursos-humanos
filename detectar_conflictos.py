"""
detectar_conflictos.py
=======================
Reporte de posibles errores de clasificación dejados por migrate_drive.py.

Se conecta SOLO a Supabase (no toca Drive) y detecta tres patrones sospechosos:

  1. SOBRE-CLASIFICACIÓN
     Empleados donde más del 70% de sus documentos son del mismo
     document_type_id — indicio de que un tipo "absorbió" archivos que no le
     correspondían. Se marcan los documentos del tipo dominante.

  2. TIPOS ÚNICOS DUPLICADOS
     Empleados con 2 o más documentos de un tipo que normalmente es único por
     persona (RUT, FOTOCOPIA_CEDULA, HOJA_DE_VIDA).
     NOTA: el esquema ya impone UNIQUE(employee_id, document_type_id), así que
     en la práctica esto solo podría dispararse si esos códigos tuvieran
     duplicados por datos heredados. Se comprueba de todos modos por seguridad.

  3. NOMBRE NO RELACIONADO AL TIPO
     Documentos cuyo nombre de archivo no comparte ninguna palabra razonable
     con el nombre/código del tipo asignado.

Salida:
  - conflictos_reporte.csv  (empleado, zona, tipo_documento_asignado,
    nombre_archivo, razon_sospecha, drive_url)
  - Resumen por consola.

Uso:
    python detectar_conflictos.py
"""

from __future__ import annotations

import csv
import unicodedata
from collections import Counter, defaultdict

from dotenv import load_dotenv

load_dotenv()

from infrastructure.supabase.client import get_supabase_client

# ── Parámetros ────────────────────────────────────────────────────────────
_OUTPUT_CSV = "conflictos_reporte.csv"

# Umbral de sobre-clasificación y mínimo de documentos para que sea relevante
# (con pocos documentos un 70% es trivial y no significa nada).
_OVERCLASS_RATIO = 0.70
_OVERCLASS_MIN_DOCS = 4

# Tipos que deberían ser únicos por persona.
_UNIQUE_TYPE_CODES = {"RUT", "FOTOCOPIA_CEDULA", "HOJA_DE_VIDA"}

# Categoría de documentos "sueltos": no representan una clasificación real,
# así que se excluyen de los tres análisis.
_EXTRA_CATEGORY = "EXTRA"

# Palabras vacías que no aportan a la comparación semántica nombre↔tipo.
_STOPWORDS = {
    "DE", "DEL", "LA", "EL", "LOS", "LAS", "Y", "O", "EN", "POR", "PARA",
    "CON", "A", "AL", "UN", "UNA", "SI", "NO", "SG", "SST", "PDF", "DOCX",
    "JPG", "JPEG", "PNG", "DOC", "FINAL", "FIRMADO", "FIRMADA", "SCAN",
    "ESCANEADO", "COPIA", "NUEVO", "NUEVA",
}

# Sinónimos extra por código: palabras que también deben considerarse "del
# tipo" aunque no aparezcan en su nombre oficial. Reduce falsos positivos del
# análisis 3 (p. ej. una cédula suele llamarse "C.C." o "documento").
_TYPE_SYNONYMS: dict[str, set[str]] = {
    "FOTOCOPIA_CEDULA": {"CC", "DOCUMENTO", "IDENTIDAD"},
    "RUT": {"DIAN", "TRIBUTARIO"},
    "HOJA_DE_VIDA": {"HV", "CURRICULUM", "CV"},
    "AFILIACION_EPS": {"SALUD", "COOSALUD", "NUEVA", "SANITAS"},
    "AFILIACION_ARL": {"ARL", "RIESGOS", "SURA", "POSITIVA"},
    "AFILIACION_COMFABOY": {"COMFABOY", "COMFA", "CAJA", "COMPENSACION"},
    "CERT_PENSION_EPS": {"PENSION", "PORVENIR", "COLPENSIONES", "PROTECCION"},
    "CERT_BANCARIA": {"BANCO", "BANCARIA", "CUENTA", "BANCOLOMBIA", "DAVIVIENDA"},
    "ANTECEDENTES": {"PROCURADURIA", "CONTRALORIA", "PONAL", "POLICIA", "JUDICIALES"},
    "REGISTRO_CIVIL": {"NACIMIENTO", "TARJETA"},
    "CONTRATO": {"OTROSI", "OTRO"},
}


def _normalize(text: str) -> str:
    """MAYÚSCULAS, sin tildes, sin espacios sobrantes. La Ñ se conserva."""
    protected = text.replace("ñ", "\0").replace("Ñ", "\0")
    nfkd = unicodedata.normalize("NFKD", protected)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.replace("\0", "Ñ").strip().upper()


def _tokens(text: str) -> set[str]:
    """Palabras significativas (>=3 letras, sin stopwords) de un texto."""
    norm = _normalize(text)
    raw = "".join(c if c.isalnum() else " " for c in norm).split()
    return {w for w in raw if len(w) >= 3 and w not in _STOPWORDS}


def _type_related_words(code: str, name: str) -> set[str]:
    """Vocabulario asociado a un tipo: nombre + código + sinónimos."""
    words = _tokens(name) | _tokens(code.replace("_", " "))
    words |= _TYPE_SYNONYMS.get(code.upper(), set())
    return words


# ───────────────────────────────────────────────────────────────────────────


def _resolve_zona(group_id: str | None, groups_by_id: dict[str, dict]) -> str:
    """Sube por parent_id hasta el grupo raíz (zona). Devuelve su nombre."""
    seen: set[str] = set()
    current = groups_by_id.get(group_id) if group_id else None
    while current and current.get("parent_id") and current["id"] not in seen:
        seen.add(current["id"])
        current = groups_by_id.get(current["parent_id"])
    return _normalize(current["name"]) if current else "(sin zona)"


def run() -> None:
    db = get_supabase_client()

    # ── Cargar catálogos ──────────────────────────────────────────────────
    employees = {
        e["id"]: e
        for e in (db.table("employees").select("id, name, group_id").execute().data or [])
    }
    groups_by_id = {
        g["id"]: g
        for g in (db.table("groups").select("id, name, parent_id").execute().data or [])
    }
    doc_types = {
        t["id"]: t
        for t in (
            db.table("document_types")
            .select("id, code, name, category")
            .execute()
            .data
            or []
        )
    }
    documents = (
        db.table("documents")
        .select("id, employee_id, document_type_id, file_name, drive_url")
        .execute()
        .data
        or []
    )

    print(f"Empleados: {len(employees)} | Tipos: {len(doc_types)} | "
          f"Documentos: {len(documents)}")

    # Documentos por empleado, ignorando la categoría EXTRA.
    docs_by_emp: dict[str, list[dict]] = defaultdict(list)
    for d in documents:
        dtype = doc_types.get(d["document_type_id"])
        if dtype and dtype.get("category") == _EXTRA_CATEGORY:
            continue
        docs_by_emp[d["employee_id"]].append(d)

    rows: list[dict] = []
    overclass_employees: set[str] = set()
    unrelated_count = 0

    for emp_id, emp_docs in docs_by_emp.items():
        emp = employees.get(emp_id)
        if emp is None:
            continue
        emp_name = emp["name"]
        zona = _resolve_zona(emp.get("group_id"), groups_by_id)

        # ── Análisis 1: sobre-clasificación ───────────────────────────────
        type_counter = Counter(d["document_type_id"] for d in emp_docs)
        total = len(emp_docs)
        dominant_type_id, dominant_n = type_counter.most_common(1)[0]
        dominant_over = (
            total >= _OVERCLASS_MIN_DOCS
            and dominant_n / total > _OVERCLASS_RATIO
        )
        if dominant_over:
            overclass_employees.add(emp_id)

        # ── Análisis 2: tipos únicos duplicados ───────────────────────────
        dup_unique_type_ids = {
            tid
            for tid, n in type_counter.items()
            if n >= 2
            and doc_types.get(tid, {}).get("code", "").upper() in _UNIQUE_TYPE_CODES
        }

        # ── Por documento: análisis 1 (dominante), 2 (dup) y 3 (nombre) ───
        for d in emp_docs:
            dtype = doc_types.get(d["document_type_id"], {})
            tipo_code = dtype.get("code", "?")
            tipo_name = dtype.get("name", "?")
            razones: list[str] = []

            if dominant_over and d["document_type_id"] == dominant_type_id:
                pct = round(100 * dominant_n / total)
                razones.append(
                    f"sobre-clasificacion: {pct}% de los documentos del empleado "
                    f"({dominant_n}/{total}) son de tipo {tipo_code}"
                )

            if d["document_type_id"] in dup_unique_type_ids:
                razones.append(
                    f"tipo unico duplicado: {tipo_code} aparece "
                    f"{type_counter[d['document_type_id']]} veces"
                )

            related = _type_related_words(tipo_code, tipo_name)
            fname_tokens = _tokens(d.get("file_name") or "")
            if related and fname_tokens and related.isdisjoint(fname_tokens):
                unrelated_count += 1
                razones.append(
                    f"nombre no relacionado: '{d.get('file_name')}' no comparte "
                    f"ninguna palabra con el tipo {tipo_code} ({tipo_name})"
                )

            if razones:
                rows.append({
                    "empleado": emp_name,
                    "zona": zona,
                    "tipo_documento_asignado": tipo_code,
                    "nombre_archivo": d.get("file_name") or "",
                    "razon_sospecha": " | ".join(razones),
                    "drive_url": d.get("drive_url") or "",
                })

    # ── Escribir CSV ──────────────────────────────────────────────────────
    fieldnames = [
        "empleado", "zona", "tipo_documento_asignado",
        "nombre_archivo", "razon_sospecha", "drive_url",
    ]
    with open(_OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # ── Resumen ───────────────────────────────────────────────────────────
    print(f"\nReporte escrito en {_OUTPUT_CSV} ({len(rows)} filas sospechosas)")
    print(f"\n{len(overclass_employees)} empleados con posible sobre-clasificación")
    print(f"{unrelated_count} documentos con nombre no relacionado al tipo")


if __name__ == "__main__":
    print("=" * 60)
    print("  Detección de conflictos de clasificación (solo lectura)")
    print("=" * 60)
    run()
