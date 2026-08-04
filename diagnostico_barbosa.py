"""
Diagnóstico SOLO-LECTURA del problema "BARBOSA muestra 0 empleados".

No modifica NADA. Consulta Supabase directamente y responde:

  1. ¿Existen los 12 empleados esperados en la tabla `employees`?
     (búsqueda por nombre con ILIKE) → id, name, group_id, is_active
  2. Para cada uno, ¿a qué grupo apunta su group_id? nombre, parent_id,
     y nombre del grupo padre.
  3. ¿Cuáles son los ids REALES de los subgrupos "Asesores" y "Logisticos"
     hijos del grupo "Barbosa" ahora mismo?
  4. Veredicto explícito: ¿los group_id de los empleados coinciden con esos
     ids actuales, apuntan a un id inexistente, o a otro grupo?

Uso:  python diagnostico_barbosa.py
"""
from dotenv import load_dotenv

load_dotenv()

from infrastructure.supabase.client import get_supabase_client

_EXPECTED_NAMES = [
    "KEVIN ANDRES ORTIZ",
    "DEISY VARGAS",
    "ALEXANDER GUIZA SANABRIA",
    "YENNY ORTIZ",
    "MARLEN CARVAJAL",
    "OCTAVIO BRITO",
    "SEBASTIAN LOPEZ",
    "ANGELMIRO BAREÑO",
    "DANIEL FERNANDO MONTES",
    "DIANA MARCELA VELANDIA",
    "GINNA COY",
    "EDGAR COBARIA",
]

# Palabras a resaltar en las búsquedas de grupos.
_BARBOSA_NAME = "BARBOSA"


def _sep(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    db = get_supabase_client()

    # ── Carga completa de grupos (para resolver árbol en memoria) ──────────
    groups_rows = db.table("groups").select("*").execute().data or []
    groups_by_id = {g["id"]: g for g in groups_rows}

    def group_name(gid):
        g = groups_by_id.get(gid)
        return g["name"] if g else None

    # ─────────────────────────────────────────────────────────────────────
    # PASO 3 (lo calculamos primero porque lo usa el veredicto):
    # ids reales de los subgrupos hijos de "Barbosa"
    # ─────────────────────────────────────────────────────────────────────
    _sep('PASO 3 — Subgrupos actuales hijos del grupo "Barbosa"')

    barbosa_groups = [
        g for g in groups_rows
        if g["name"].strip().upper() == _BARBOSA_NAME and g.get("parent_id")
    ]
    # "Barbosa" como ZONA suele ser hija de RETIRADOS o raíz; buscamos todos los
    # grupos llamados Barbosa y mostramos su contexto para no asumir.
    all_barbosa = [g for g in groups_rows if g["name"].strip().upper() == _BARBOSA_NAME]

    if not all_barbosa:
        print('  ⚠ No existe NINGÚN grupo llamado "Barbosa" en la tabla groups.')
    for bg in all_barbosa:
        parent = group_name(bg.get("parent_id"))
        print(f'  Grupo "Barbosa"  id={bg["id"]}  parent_id={bg.get("parent_id")} '
              f'(padre="{parent}")')

    # Recolecta subgrupos hijos de CUALQUIER grupo Barbosa
    barbosa_ids = {g["id"] for g in all_barbosa}
    subgroups = [g for g in groups_rows if g.get("parent_id") in barbosa_ids]

    subgroup_id_by_name = {}
    if not subgroups:
        print("  ⚠ Ese grupo Barbosa no tiene subgrupos hijos.")
    for sg in subgroups:
        print(f'    └─ subgrupo "{sg["name"]}"  id={sg["id"]}  '
              f'parent_id={sg["parent_id"]}')
        subgroup_id_by_name[sg["name"].strip().upper()] = sg["id"]

    asesores_id = subgroup_id_by_name.get("ASESORES")
    logisticos_id = subgroup_id_by_name.get("LOGISTICOS")
    valid_target_ids = {i for i in (asesores_id, logisticos_id) if i}
    # También aceptamos como "válido correcto" el propio Barbosa por si los
    # empleados cuelgan directo de la zona.
    print(f"\n  → id Asesores   = {asesores_id}")
    print(f"  → id Logisticos = {logisticos_id}")
    print(f"  → id(s) Barbosa = {sorted(barbosa_ids)}")

    # ─────────────────────────────────────────────────────────────────────
    # PASO 1 + 2 — empleados esperados y a qué grupo apuntan
    # ─────────────────────────────────────────────────────────────────────
    _sep("PASO 1 y 2 — Empleados esperados: existencia y grupo al que apuntan")

    found_total = 0
    for name in _EXPECTED_NAMES:
        # ILIKE tolerante: primera palabra + última palabra, y también el nombre completo.
        rows = (
            db.table("employees")
            .select("id,name,group_id,is_active")
            .ilike("name", f"%{name}%")
            .execute()
            .data
        ) or []

        # Fallback: si no hubo match exacto por el string completo, probar por
        # apellido (última palabra) para detectar variaciones de orden/tildes.
        if not rows:
            last = name.split()[-1]
            rows = (
                db.table("employees")
                .select("id,name,group_id,is_active")
                .ilike("name", f"%{last}%")
                .execute()
                .data
            ) or []
            tag = f'(no exacto; búsqueda por "%{last}%")'
        else:
            tag = ""

        if not rows:
            print(f'\n  ✗ "{name}"  → NO ENCONTRADO {tag}')
            continue

        for r in rows:
            found_total += 1
            gid = r.get("group_id")
            g = groups_by_id.get(gid)
            if gid is None:
                grp_desc = "group_id = NULL (sin grupo)"
            elif g is None:
                grp_desc = f"group_id={gid}  → ⚠ ESE GRUPO NO EXISTE en groups"
            else:
                parent = group_name(g.get("parent_id"))
                grp_desc = (f'group_id={gid}  → grupo="{g["name"]}"  '
                            f'parent_id={g.get("parent_id")} (padre="{parent}")')
            print(f'\n  • BD name="{r["name"]}"  {tag}')
            print(f'      id={r["id"]}  is_active={r["is_active"]}')
            print(f'      {grp_desc}')

    # ─────────────────────────────────────────────────────────────────────
    # PASO 4 — Veredicto
    # ─────────────────────────────────────────────────────────────────────
    _sep("PASO 4 — Veredicto (coincidencia de group_id)")

    # Reunimos los group_id de todos los empleados que hacen match con la zona
    # Barbosa por nombre, para clasificarlos.
    match_names_ilike = "%".join([""] )  # placeholder no usado
    # Recolectamos empleados por los nombres esperados otra vez, agregando group_id.
    employee_gids = []
    for name in _EXPECTED_NAMES:
        rows = (
            db.table("employees").select("id,name,group_id")
            .ilike("name", f"%{name}%").execute().data
        ) or []
        if not rows:
            last = name.split()[-1]
            rows = (
                db.table("employees").select("id,name,group_id")
                .ilike("name", f"%{last}%").execute().data
            ) or []
        for r in rows:
            employee_gids.append((r["name"], r.get("group_id")))

    n_match_subgroup = 0
    n_match_barbosa = 0
    n_orphan = 0       # apunta a id inexistente
    n_null = 0
    n_other = 0        # existe pero pertenece a otra rama
    other_examples = []

    for nm, gid in employee_gids:
        if gid is None:
            n_null += 1
        elif gid in valid_target_ids:
            n_match_subgroup += 1
        elif gid in barbosa_ids:
            n_match_barbosa += 1
        elif gid not in groups_by_id:
            n_orphan += 1
        else:
            n_other += 1
            g = groups_by_id[gid]
            other_examples.append((nm, g["name"], gid))

    print(f"  Empleados evaluados: {len(employee_gids)}")
    print(f"    • group_id == subgrupo Asesores/Logisticos actual : {n_match_subgroup}")
    print(f"    • group_id == zona Barbosa (cuelgan directo)      : {n_match_barbosa}")
    print(f"    • group_id apunta a un id que YA NO EXISTE         : {n_orphan}")
    print(f"    • group_id pertenece a OTRO grupo (otra rama)      : {n_other}")
    print(f"    • group_id NULL                                    : {n_null}")

    if other_examples:
        print("\n  Ejemplos de 'otro grupo':")
        for nm, gname, gid in other_examples[:10]:
            print(f'    - "{nm}" → "{gname}" (id={gid})')

    print("\n  CONCLUSIÓN:")
    if n_orphan and not n_match_subgroup:
        print("    ✗ Los empleados apuntan a group_id que YA NO EXISTEN. Los subgrupos")
        print("      de Barbosa fueron RE-CREADOS con ids nuevos y los empleados quedaron")
        print("      huérfanos → por eso la pantalla muestra 0.")
    elif n_other and not n_match_subgroup:
        print("    ✗ Los group_id existen pero pertenecen a OTRA rama, no a los subgrupos")
        print("      actuales de Barbosa.")
    elif n_match_subgroup and not (n_orphan or n_other):
        print("    ✓ Los group_id SÍ coinciden con los subgrupos actuales de Barbosa.")
        print("      El problema estaría en la CONSULTA de la pantalla, no en los datos.")
    else:
        print("    ⚠ Situación mixta (ver conteos arriba).")

    print()


if __name__ == "__main__":
    main()
