"""
Reconciliación del group_id de los empleados INACTIVOS (retirados), usando
Google Drive como FUENTE DE VERDAD.

Contexto (ver diagnosticar_retirados.py):
  159 retirados de Tunja tienen group_id apuntando a la zona TUNJA ACTIVA en
  lugar del subgrupo RETIRADOS/TUNJA. Sus archivos en Drive SÍ están bien
  ubicados bajo RETIRADOS/RETIRADOS {ZONA}. El daño es puramente un dato
  incorrecto en Supabase — Drive no necesita tocarse.

Qué hace:
  • Reutiliza la lógica de diagnosticar_retirados.py para encontrar los
    inactivos cuyo group_id no coincide con su ubicación física real en Drive.
  • Muestra el resumen ANTES de tocar nada y pide confirmación (s/n).
  • Si se confirma, actualiza SOLO la columna group_id en `employees` al id
    correcto de RETIRADOS/{zona} según cada caso.
  • Los "no verificables" (sin documentos, p.ej. PREJURIDICO) se dejan intactos
    y se reportan aparte.
  • Genera reconciliacion_retirados_log.csv.

Garantías (mismo patrón de seguridad que reconciliar_grupos.py):
  • Hacia Drive es SOLO LECTURA (solo metadata de parents; nunca mueve/edita).
  • Solo modifica la columna group_id de la tabla `employees`. Nada más.
  • Empleado sin documentos verificables → no se toca.

Uso:  python reconciliar_retirados.py
"""
from __future__ import annotations

import csv
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

from infrastructure.google_drive.drive_adapter import _build_service
from infrastructure.supabase.client import get_supabase_client
from infrastructure.supabase.document_repository import SupabaseDocumentRepository

# Reutilizamos la misma maquinaria del diagnóstico y del script de activos.
from reconciliar_grupos import (
    DriveReader,
    GroupIndex,
    _ancestry_from_file,
)
from diagnosticar_retirados import (
    _RETIRADOS,
    _chain_names,
    _interpret,
)

_LOG_CSV = "reconciliacion_retirados_log.csv"


def main() -> None:
    db = get_supabase_client()
    doc_repo = SupabaseDocumentRepository(db)
    reader = DriveReader(_build_service())

    group_rows = db.table("groups").select("id, name, parent_id").execute().data or []
    groups = GroupIndex(group_rows)
    roots = groups._roots_by_name  # solo lectura

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

    to_fix: list[dict] = []        # {emp, current_name, new_group, new_name}
    unverifiable: list[dict] = []  # {emp, reason}
    ok_count = 0

    for emp in employees:
        current_gid = emp.get("group_id")

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

        _drive_under_ret, zona = _interpret(names, roots)

        # Grupo correcto = RETIRADOS/{zona} (según la ubicación física real).
        target_group = groups.resolve(_RETIRADOS, zona) if zona else None
        if target_group is None:
            unverifiable.append({
                "emp": emp,
                "reason": (
                    f"no existe en Supabase el grupo '{_RETIRADOS}/{zona}'"
                    if zona else "no se pudo detectar la zona real en Drive"
                ),
            })
            continue

        if target_group["id"] == current_gid:
            ok_count += 1
            continue

        to_fix.append({
            "emp": emp,
            "current_name": groups.name(current_gid),
            "new_group": target_group,
            "new_name": groups.name(target_group["id"]),
        })

    revisados = len(employees) - len(unverifiable)

    # ── Resumen ───────────────────────────────────────────────────────────
    print("=" * 78)
    print("RESUMEN — RECONCILIACIÓN DE RETIRADOS")
    print("=" * 78)
    print(f"  Revisados (con documentos): {revisados}")
    print(f"  Correctos (ya bien ubicados): {ok_count}")
    print(f"  No verificables (intactos): {len(unverifiable)}")
    print(f"  Mal ubicados (a corregir): {len(to_fix)}\n")

    if to_fix:
        w_name = max(len("Empleado"), max(len(f["emp"]["name"]) for f in to_fix))
        w_cur = max(len("Grupo actual (BD)"), max(len(f["current_name"]) for f in to_fix))
        w_new = max(len("Grupo correcto (Drive)"), max(len(f["new_name"]) for f in to_fix))
        print(f"  {'Empleado':<{w_name}}   {'Grupo actual (BD)':<{w_cur}}   "
              f"{'Grupo correcto (Drive)':<{w_new}}")
        print(f"  {'-'*w_name}   {'-'*w_cur}   {'-'*w_new}")
        for f in to_fix:
            print(f"  {f['emp']['name']:<{w_name}}   {f['current_name']:<{w_cur}}   "
                  f"{f['new_name']:<{w_new}}")
        print(f"\n  Total: {len(to_fix)} empleados a corregir")

    if unverifiable:
        print(f"\n  No verificables ({len(unverifiable)}) — se dejan INTACTOS:")
        for u in unverifiable:
            print(f"    - {u['emp']['name']} "
                  f"[BD: {groups.name(u['emp'].get('group_id'))}]: {u['reason']}")

    # ── Confirmación y corrección ─────────────────────────────────────────
    log_rows: list[dict] = []

    if not to_fix:
        print("\n✓ No hay empleados retirados mal ubicados. Nada que corregir.")
    else:
        resp = input(f"\n¿Corregir estos {len(to_fix)} empleados? (s/n): ").strip().lower()
        if resp != "s":
            print("Cancelado. No se modificó nada.")
            for f in to_fix:
                log_rows.append({
                    "empleado": f["emp"]["name"],
                    "grupo_anterior": f["current_name"],
                    "grupo_nuevo": f["new_name"],
                    "resultado": "cancelado",
                })
        else:
            for f in to_fix:
                emp = f["emp"]
                try:
                    (
                        db.table("employees")
                        .update({"group_id": f["new_group"]["id"]})
                        .eq("id", emp["id"])
                        .execute()
                    )
                    resultado = "corregido"
                    print(f"  ✓ {emp['name']}: {f['current_name']} → {f['new_name']}")
                except Exception as exc:  # noqa: BLE001
                    resultado = f"error: {exc}"
                    print(f"  ✗ {emp['name']}: {resultado}")
                log_rows.append({
                    "empleado": emp["name"],
                    "grupo_anterior": f["current_name"],
                    "grupo_nuevo": f["new_name"],
                    "resultado": resultado,
                })

    # Añade los no verificables al log (trazabilidad; no se tocaron).
    for u in unverifiable:
        log_rows.append({
            "empleado": u["emp"]["name"],
            "grupo_anterior": groups.name(u["emp"].get("group_id")),
            "grupo_nuevo": "",
            "resultado": f"no verificable, intacto ({u['reason']})",
        })

    # ── Log CSV ───────────────────────────────────────────────────────────
    if log_rows:
        with open(_LOG_CSV, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["empleado", "grupo_anterior", "grupo_nuevo", "resultado"],
            )
            writer.writeheader()
            writer.writerows(log_rows)
        print(f"\nLog escrito en {_LOG_CSV} ({len(log_rows)} filas).")


if __name__ == "__main__":
    main()
