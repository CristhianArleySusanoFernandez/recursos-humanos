"""
cleanup_test.py
===============
Limpia los datos de prueba dejados por una corrida `migrate_drive.py --test`.

Elimina en Supabase:
  1. Los documentos (documents) del empleado DAVID DIAZ.
  2. Sus marcas "No Aplica" (document_na).
  3. El propio registro en employees.
  4. Los tipos EXTRA_* creados durante la prueba (document_types).

NO toca ningún archivo de Google Drive: solo borra registros en Supabase.

Uso:
    python cleanup_test.py
"""

from __future__ import annotations

import sys
import unicodedata

from dotenv import load_dotenv

load_dotenv()

from infrastructure.supabase.client import get_supabase_client

# Empleado de prueba a eliminar (comparación normalizada, sin tildes/mayúsc.).
_TARGET_NAME = "DAVID DIAZ"

# Sentinela para los .neq() (un UUID que nunca existirá) al borrar en bloque.
_NEVER_ID = "00000000-0000-0000-0000-000000000000"


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().upper()


def run() -> None:
    db = get_supabase_client()

    # ── Localizar al empleado por nombre normalizado ──────────────────────
    resp = db.table("employees").select("id, name").execute()
    matches = [
        row for row in (resp.data or [])
        if _normalize(row["name"]) == _TARGET_NAME
    ]

    if not matches:
        print(f"No se encontró ningún empleado '{_TARGET_NAME}'. Nada que borrar.")
    else:
        for emp in matches:
            emp_id = emp["id"]
            print(f"Eliminando empleado {emp['name']} ({emp_id})")

            docs = (
                db.table("documents").delete().eq("employee_id", emp_id).execute()
            )
            print(f"  documents eliminados:    {len(docs.data or [])}")

            na = (
                db.table("document_na").delete().eq("employee_id", emp_id).execute()
            )
            print(f"  document_na eliminados:  {len(na.data or [])}")

            emp_del = db.table("employees").delete().eq("id", emp_id).execute()
            print(f"  employees eliminados:    {len(emp_del.data or [])}")

    # ── Eliminar los tipos EXTRA_* creados en la prueba ───────────────────
    # like('code', 'EXTRA\_%') escaparía el guion bajo; en la práctica todos
    # los códigos autogenerados empiezan por 'EXTRA_' así que basta el prefijo.
    extra = (
        db.table("document_types")
        .delete()
        .like("code", "EXTRA_%")
        .execute()
    )
    print(f"\nTipos EXTRA_* eliminados en document_types: {len(extra.data or [])}")
    if extra.data:
        for row in extra.data:
            print(f"  - {row.get('code')}  ({row.get('name')})")

    print("\n✓ Limpieza completada.")


if __name__ == "__main__":
    print("=" * 60)
    print("  Limpieza de datos de prueba (DAVID DIAZ + tipos EXTRA_*)")
    print("=" * 60)
    confirm = input(
        "\nEsto elimina registros en Supabase (no toca Drive). ¿Continuar? (s/n): "
    ).strip().lower()
    if confirm != "s":
        print("Cancelado.")
        sys.exit(0)
    run()
