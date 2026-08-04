"""
Reconciliación de la ubicación (group_id) de los empleados usando Google Drive
como FUENTE DE VERDAD.

El group_id en Supabase puede estar mal (la migración resolvía el subgrupo solo
por nombre, sin verificar la zona). Este script NO confía en ese group_id: para
cada empleado activo sube la cadena de carpetas de uno de sus documentos en Drive
    archivo → carpeta empleado → carpeta categoría → carpeta zona
y lee los nombres REALES de categoría y zona directamente desde Drive. Con eso
determina el grupo correcto en Supabase (por nombre + parent) y corrige el
group_id si difiere.

Garantías:
  • Hacia Drive es SOLO LECTURA (solo metadata de parents; nunca mueve/edita).
  • Solo modifica la columna group_id de la tabla `employees`. Nada más.
  • Empleado sin documentos → "no verificable", no se toca.
  • Pausas cortas entre llamadas para respetar rate limits de Drive.

Uso:  python reconciliar_grupos.py
"""
from __future__ import annotations

import csv
import time
import unicodedata
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

from infrastructure.google_drive.drive_adapter import _build_service
from infrastructure.supabase.client import get_supabase_client
from infrastructure.supabase.document_repository import SupabaseDocumentRepository

_FOLDER_MIME = "application/vnd.google-apps.folder"
_LOG_CSV = "reconciliacion_log.csv"
_DRIVE_PAUSE = 0.15  # segundos entre llamadas a Drive (suaviza el rate limit)


# ---------------------------------------------------------------------------
# Normalización (idéntica en espíritu a la de migrate_drive: preserva Ñ)
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    if not text:
        return ""
    tmp = text.replace("Ñ", "\0").replace("ñ", "\0")
    tmp = unicodedata.normalize("NFKD", tmp)
    tmp = "".join(c for c in tmp if not unicodedata.combining(c))
    tmp = tmp.replace("\0", "Ñ")
    return tmp.strip().upper()


def _strip_retirados_prefix(name: str) -> str:
    for prefix in ("RETIRADOS_", "RETIRADOS ", "RETIRADOS"):
        if name.startswith(prefix):
            cleaned = name[len(prefix):].lstrip("_ ").strip()
            return cleaned or name
    return name


# ---------------------------------------------------------------------------
# Cliente de Drive: lectura de metadata de carpetas (solo lectura)
# ---------------------------------------------------------------------------
class DriveReader:
    def __init__(self, service) -> None:
        self._svc = service
        self._cache: dict[str, dict] = {}  # file_id → {id, name, parents, mimeType}

    def get_meta(self, file_id: str) -> dict | None:
        if file_id in self._cache:
            return self._cache[file_id]
        try:
            meta = (
                self._svc.files()
                .get(
                    fileId=file_id,
                    fields="id, name, parents, mimeType",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 — queremos continuar con otros
            print(f"    ⚠ Drive get({file_id}) falló: {exc}")
            self._cache[file_id] = None
            return None
        time.sleep(_DRIVE_PAUSE)
        self._cache[file_id] = meta
        return meta

    def first_parent(self, meta: dict | None) -> str | None:
        if not meta:
            return None
        parents = meta.get("parents") or []
        return parents[0] if parents else None


def _ancestry_from_file(reader: DriveReader, file_id: str) -> list[dict]:
    """
    Devuelve la cadena de CARPETAS ancestro (de más cercana a más lejana):
        [carpeta_empleado, carpeta_categoria, carpeta_zona, ...]
    Empieza en el primer parent del archivo (el archivo mismo no se incluye).
    """
    chain: list[dict] = []
    file_meta = reader.get_meta(file_id)
    parent_id = reader.first_parent(file_meta)
    guard = 0
    while parent_id and guard < 12:
        guard += 1
        pmeta = reader.get_meta(parent_id)
        if not pmeta:
            break
        chain.append(pmeta)
        parent_id = reader.first_parent(pmeta)
    return chain


# ---------------------------------------------------------------------------
# Resolución del grupo correcto en Supabase por (categoria, zona) reales
# ---------------------------------------------------------------------------
class GroupIndex:
    """Índice de grupos de Supabase por (nombre_normalizado, parent_id)."""

    def __init__(self, rows: list[dict]) -> None:
        self._by_id: dict[str, dict] = {r["id"]: r for r in rows}
        self._by_key: dict[tuple[str, str | None], dict] = {}
        self._roots_by_name: dict[str, dict] = {}
        for r in rows:
            key = (_normalize(r["name"]), r.get("parent_id"))
            self._by_key[key] = r
            if r.get("parent_id") is None:
                self._roots_by_name[_normalize(r["name"])] = r

    def resolve(self, zona_name: str, cat_name: str) -> dict | None:
        """Grupo subgrupo cuyo nombre == cat_name y cuyo padre == zona raíz."""
        zona_name = _normalize(zona_name)
        cat_name = _normalize(cat_name)
        if zona_name == "RETIRADOS":
            cat_name = _strip_retirados_prefix(cat_name)
        zona = self._roots_by_name.get(zona_name)
        if zona is None:
            return None
        return self._by_key.get((cat_name, zona["id"]))

    def name(self, group_id: str | None) -> str:
        if not group_id:
            return "(sin grupo)"
        g = self._by_id.get(group_id)
        if not g:
            return f"(id inexistente {group_id})"
        parent = self._by_id.get(g.get("parent_id"))
        pref = f"{_normalize(parent['name'])}/" if parent else ""
        return f"{pref}{_normalize(g['name'])}"


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
def main() -> None:
    db = get_supabase_client()
    doc_repo = SupabaseDocumentRepository(db)
    reader = DriveReader(_build_service())

    # Índice de grupos.
    group_rows = db.table("groups").select("id, name, parent_id").execute().data or []
    groups = GroupIndex(group_rows)

    # Empleados activos.
    employees = (
        db.table("employees")
        .select("id, name, group_id, is_active")
        .eq("is_active", True)
        .order("name")
        .execute()
        .data
    ) or []

    print(f"Empleados activos a revisar: {len(employees)}\n")

    to_fix: list[dict] = []       # {emp, current_gid, current_name, new_group, new_name}
    unverifiable: list[dict] = []  # {emp, reason}
    ok_count = 0

    for emp in employees:
        emp_id = emp["id"]
        emp_name = emp["name"]
        current_gid = emp.get("group_id")

        docs = doc_repo.get_by_employee(UUID(emp_id))
        if not docs:
            unverifiable.append({"emp": emp, "reason": "sin documentos"})
            continue

        # Usa el primer documento con drive_file_id.
        doc = next((d for d in docs if d.drive_file_id), None)
        if doc is None:
            unverifiable.append({"emp": emp, "reason": "documentos sin drive_file_id"})
            continue

        chain = _ancestry_from_file(reader, doc.drive_file_id)
        # chain = [empleado, categoria, zona, ...] (nombres reales de Drive)
        if len(chain) < 3:
            unverifiable.append({
                "emp": emp,
                "reason": f"cadena de carpetas incompleta en Drive ({len(chain)} niveles)",
            })
            continue

        real_cat_name = chain[1]["name"]   # carpeta categoría (subgrupo)
        real_zona_name = chain[2]["name"]  # carpeta zona (raíz)

        target_group = groups.resolve(real_zona_name, real_cat_name)
        if target_group is None:
            unverifiable.append({
                "emp": emp,
                "reason": (
                    f"no existe en Supabase el grupo "
                    f"'{_normalize(real_zona_name)}/{_normalize(real_cat_name)}'"
                ),
            })
            continue

        if target_group["id"] == current_gid:
            ok_count += 1
            continue

        to_fix.append({
            "emp": emp,
            "current_gid": current_gid,
            "current_name": groups.name(current_gid),
            "new_group": target_group,
            "new_name": groups.name(target_group["id"]),
        })

    # ── Resumen ───────────────────────────────────────────────────────────
    print("=" * 78)
    print("RESUMEN")
    print("=" * 78)
    print(f"  Revisados (con documentos): {len(employees) - len(unverifiable)}")
    print(f"  Correctos (ya bien ubicados): {ok_count}")
    print(f"  No verificables: {len(unverifiable)}")
    print(f"  Mal ubicados (a corregir): {len(to_fix)}\n")

    if to_fix:
        w_name = max(len(f["emp"]["name"]) for f in to_fix)
        w_name = max(w_name, len("Empleado"))
        w_cur = max((len(f["current_name"]) for f in to_fix), default=0)
        w_cur = max(w_cur, len("Grupo actual (BD)"))
        print(f"  {'Empleado':<{w_name}}   {'Grupo actual (BD)':<{w_cur}}   Grupo real (Drive)")
        print(f"  {'-'*w_name}   {'-'*w_cur}   {'-'*20}")
        for f in to_fix:
            print(f"  {f['emp']['name']:<{w_name}}   "
                  f"{f['current_name']:<{w_cur}}   {f['new_name']}")
        print(f"\n  Total: {len(to_fix)} empleados mal ubicados "
              f"de {len(employees) - len(unverifiable)} activos revisados")

    if unverifiable:
        print(f"\n  No verificables ({len(unverifiable)}):")
        for u in unverifiable:
            print(f"    - {u['emp']['name']}: {u['reason']}")

    # ── Confirmación ──────────────────────────────────────────────────────
    log_rows: list[dict] = []

    if not to_fix:
        print("\n✓ No hay empleados mal ubicados. Nada que corregir.")
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

    # Añade los no verificables al log para tener trazabilidad completa.
    for u in unverifiable:
        log_rows.append({
            "empleado": u["emp"]["name"],
            "grupo_anterior": groups.name(u["emp"].get("group_id")),
            "grupo_nuevo": "",
            "resultado": f"no verificable ({u['reason']})",
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
