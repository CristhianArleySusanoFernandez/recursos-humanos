"""
DIAGNÓSTICO (solo lectura) de la ubicación de los empleados INACTIVOS (retirados).

Contexto:
  reconciliar_grupos.py solo revisó empleados ACTIVOS. Los retirados nunca se
  verificaron. Se sospecha el mismo bug de la migración anterior al fix de
  (nombre, parent_id): subgrupos como "TUNJA" dentro de RETIRADOS pudieron
  resolver a la ZONA RAÍZ activa "TUNJA" en lugar del subgrupo RETIRADOS/TUNJA
  — tanto en el group_id de Supabase como en la carpeta física de Drive.

Qué hace (NO modifica NADA, ni Supabase ni Drive):
  Para cada empleado con is_active=False:
    • Sube la cadena de carpetas de uno de sus documentos en Drive
      (archivo → empleado → ... → raíz) y lee los nombres REALES.
    • Determina si físicamente está bajo la rama RETIRADOS o no.
    • Compara el group_id actual (BD) contra esa ubicación física real.
  Luego imprime:
    1. Cuántos están correctamente bajo RETIRADOS/{zona} en BD *y* en Drive.
    2. Cuántos tienen el group_id apuntando a un lugar distinto del físico.
    3. Verificación específica de RETIRADOS/TUNJA:
       - empleados inactivos con group_id == RETIRADOS/TUNJA (BD), y
       - empleados retirados cuyos archivos están físicamente dentro de la
         zona TUNJA ACTIVA (fuera de la rama Retirados).

Uso:  python diagnosticar_retirados.py
"""
from __future__ import annotations

from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

from infrastructure.google_drive.drive_adapter import _build_service
from infrastructure.supabase.client import get_supabase_client
from infrastructure.supabase.document_repository import SupabaseDocumentRepository

# Reutilizamos exactamente la misma maquinaria del script de reconciliación.
from reconciliar_grupos import (
    DriveReader,
    GroupIndex,
    _ancestry_from_file,
    _normalize,
    _strip_retirados_prefix,
)

_RETIRADOS = "RETIRADOS"


def _chain_names(chain: list[dict]) -> list[str]:
    """Nombres normalizados de la cadena de carpetas (empleado primero → raíz)."""
    return [_normalize(m.get("name", "")) for m in chain]


def _is_retirados_folder(name: str) -> bool:
    """True si la carpeta ES la raíz 'RETIRADOS' (no una zona 'RETIRADOS TUNJA')."""
    return name == _RETIRADOS


def _interpret(chain_names: list[str], roots: dict) -> tuple[bool, str | None]:
    """
    Interpreta la ubicación física real a partir de los nombres de carpeta.

    Estructura real observada en Drive:
        .../ RETIRADOS / "RETIRADOS {ZONA}" / <empleado> / <archivo>
    (la carpeta de zona lleva el prefijo, p.ej. "RETIRADOS TUNJA", y contiene
    directamente al empleado — no hay nivel de categoría como en los activos).

    Devuelve (bajo_retirados, zona):
      • bajo_retirados: True si existe una carpeta ancestro llamada exactamente
        "RETIRADOS" (la rama de retirados).
      • zona: nombre de zona (TUNJA, BARBOSA, ...) sin el prefijo RETIRADOS.
    """
    under_ret = any(_is_retirados_folder(n) for n in chain_names)

    if under_ret:
        # La carpeta inmediatamente sobre el empleado es la zona ("RETIRADOS X").
        zona = _strip_retirados_prefix(chain_names[1]) if len(chain_names) >= 2 else None
        return True, zona

    # No está bajo la rama RETIRADOS: sería una "fuga" a una zona ACTIVA.
    # Buscamos la zona raíz activa (de la raíz hacia el empleado).
    zona = None
    for n in reversed(chain_names):
        cand = _strip_retirados_prefix(n)
        if cand in roots and cand != _RETIRADOS:
            zona = cand
            break
    if zona is None and len(chain_names) >= 3:
        zona = chain_names[2]
    return False, zona


def main() -> None:
    db = get_supabase_client()
    doc_repo = SupabaseDocumentRepository(db)
    reader = DriveReader(_build_service())

    group_rows = db.table("groups").select("id, name, parent_id").execute().data or []
    groups = GroupIndex(group_rows)
    roots = groups._roots_by_name  # {nombre_normalizado: row}  (solo lectura)
    by_id = groups._by_id

    retirados_root = roots.get(_RETIRADOS)
    if retirados_root is None:
        print("⚠ No existe una zona raíz 'RETIRADOS' en Supabase. Abortando.")
        return
    retirados_root_id = retirados_root["id"]

    def bd_is_under_retirados(gid: str | None) -> bool:
        g = by_id.get(gid) if gid else None
        if not g:
            return False
        if g["id"] == retirados_root_id:
            return True
        return g.get("parent_id") == retirados_root_id

    # Empleados inactivos.
    employees = (
        db.table("employees")
        .select("id, name, group_id, is_active")
        .eq("is_active", False)
        .order("name")
        .execute()
        .data
    ) or []

    print(f"Empleados INACTIVOS (retirados) a revisar: {len(employees)}\n")

    ok: list[dict] = []           # bien en BD y en Drive
    misplaced: list[dict] = []    # group_id ≠ ubicación física real
    unverifiable: list[dict] = []  # sin docs / cadena incompleta / no resuelve

    for emp in employees:
        emp_name = emp["name"]
        current_gid = emp.get("group_id")
        current_name = groups.name(current_gid)

        docs = doc_repo.get_by_employee(UUID(emp["id"]))
        doc = next((d for d in docs if d.drive_file_id), None) if docs else None
        if doc is None:
            unverifiable.append({"emp": emp, "reason": "sin documentos con drive_file_id"})
            continue

        chain = _ancestry_from_file(reader, doc.drive_file_id)
        names = _chain_names(chain)
        if len(names) < 3:
            unverifiable.append({
                "emp": emp,
                "reason": f"cadena de carpetas incompleta en Drive ({len(names)} niveles)",
            })
            continue

        drive_under_ret, zona = _interpret(names, roots)
        physical_path = " / ".join(reversed(names))  # de raíz → empleado

        # Grupo correcto = RETIRADOS/{zona} (todo retirado debería colgar de ahí).
        correct_group = groups.resolve(_RETIRADOS, zona) if zona else None
        correct_name = (
            groups.name(correct_group["id"]) if correct_group
            else (f"{_RETIRADOS}/{zona} (no existe en BD)" if zona else "(zona no detectada)")
        )

        bd_under_ret = bd_is_under_retirados(current_gid)
        bd_ok = bool(correct_group) and current_gid == correct_group["id"]

        record = {
            "emp": emp,
            "current_gid": current_gid,
            "current_name": current_name,
            "physical_path": physical_path,
            "drive_under_ret": drive_under_ret,
            "zona": zona,
            "correct_name": correct_name,
        }

        if bd_ok and drive_under_ret:
            ok.append(record)
        else:
            misplaced.append(record)

    revisados = len(employees) - len(unverifiable)

    # ── Resumen ───────────────────────────────────────────────────────────
    print("=" * 82)
    print("RESUMEN — EMPLEADOS INACTIVOS")
    print("=" * 82)
    print(f"  Revisados (con documentos verificables): {revisados}")
    print(f"  Correctos (BD y Drive bajo RETIRADOS/zona): {len(ok)}")
    print(f"  Mal ubicados (group_id ≠ ubicación física): {len(misplaced)}")
    print(f"  No verificables: {len(unverifiable)}\n")

    if misplaced:
        w_name = max(len("Empleado"), max(len(r["emp"]["name"]) for r in misplaced))
        w_cur = max(len("Grupo actual (BD)"), max(len(r["current_name"]) for r in misplaced))
        w_phys = max(len("Ubicación física (Drive)"),
                     max(len(r["physical_path"]) for r in misplaced))
        print("  MAL UBICADOS:")
        print(f"  {'Empleado':<{w_name}}   {'Grupo actual (BD)':<{w_cur}}   "
              f"{'Ubicación física (Drive)':<{w_phys}}   Debería ser")
        print(f"  {'-'*w_name}   {'-'*w_cur}   {'-'*w_phys}   {'-'*22}")
        for r in misplaced:
            print(f"  {r['emp']['name']:<{w_name}}   {r['current_name']:<{w_cur}}   "
                  f"{r['physical_path']:<{w_phys}}   {r['correct_name']}")
        print()

    if unverifiable:
        print(f"  NO VERIFICABLES ({len(unverifiable)}):")
        for u in unverifiable:
            print(f"    - {u['emp']['name']} "
                  f"[BD: {groups.name(u['emp'].get('group_id'))}]: {u['reason']}")
        print()

    # ── Verificación específica RETIRADOS/TUNJA vs TUNJA activa ────────────
    print("=" * 82)
    print("VERIFICACIÓN ESPECÍFICA: RETIRADOS/TUNJA")
    print("=" * 82)

    ret_tunja = groups.resolve(_RETIRADOS, "TUNJA")
    tunja_activa = roots.get("TUNJA")
    tunja_activa_id = tunja_activa["id"] if tunja_activa else None

    if ret_tunja is None:
        print("  ⚠ No existe el subgrupo RETIRADOS/TUNJA en Supabase.")
    else:
        cnt_bd = (
            db.table("employees")
            .select("id", count="exact")
            .eq("is_active", False)
            .eq("group_id", ret_tunja["id"])
            .execute()
            .count
        )
        print(f"  (a) Inactivos con group_id == RETIRADOS/TUNJA (BD): {cnt_bd}")

    # Físicamente dentro de la rama RETIRADOS, zona TUNJA (ubicación correcta).
    fisicos_ret_tunja = [
        r for r in (ok + misplaced)
        if r["drive_under_ret"] and r["zona"] == "TUNJA"
    ]
    print(f"  (b) Retirados con archivos FÍSICAMENTE en RETIRADOS/TUNJA: "
          f"{len(fisicos_ret_tunja)}")

    # El bug real: están en RETIRADOS/TUNJA físicamente, pero su group_id (BD)
    # apunta a la ZONA TUNJA ACTIVA (raíz) en lugar del subgrupo RETIRADOS/TUNJA.
    bug_bd_tunja_activa = [
        r for r in fisicos_ret_tunja if r["current_gid"] == tunja_activa_id
    ]
    print(f"  (c) De esos, con group_id apuntando a la TUNJA ACTIVA (bug): "
          f"{len(bug_bd_tunja_activa)}")

    # Fuga física: retirados cuyos archivos están dentro de la zona TUNJA activa.
    fuga_fisica_tunja = [
        r for r in misplaced
        if not r["drive_under_ret"] and r["zona"] == "TUNJA"
    ]
    print(f"  (d) Retirados con archivos FÍSICAMENTE en la zona TUNJA ACTIVA "
          f"(fuera de Retirados): {len(fuga_fisica_tunja)}")
    for r in fuga_fisica_tunja:
        print(f"        - {r['emp']['name']}  →  {r['physical_path']}")

    print("\n(Diagnóstico de solo lectura: no se modificó ningún dato ni carpeta.)")


if __name__ == "__main__":
    main()
