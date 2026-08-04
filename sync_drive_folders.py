"""
sync_drive_folders.py
---------------------
Crea las carpetas de Drive para todos los grupos de la BD (si no existen)
y guarda el drive_folder_id resultante en cada registro.

Jerarquía esperada en Drive:
    <GOOGLE_DRIVE_ROOT_FOLDER_ID>/
        <grupo raíz>/          ← nivel 1 (parent_id IS NULL)
            <subgrupo>/        ← nivel 2 (parent_id = raíz)

Uso:
    python sync_drive_folders.py

Requiere que .env esté configurado y que el token OAuth sea válido
(corre setup_google_auth.py antes si es necesario).
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Importaciones del proyecto (tras cargar .env)
# ---------------------------------------------------------------------------

from infrastructure.google_drive.drive_adapter import GoogleDriveAdapter
from infrastructure.supabase.group_repository import SupabaseGroupRepository


def sync() -> None:
    root_folder_id = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
    if not root_folder_id:
        print("ERROR: Falta GOOGLE_DRIVE_ROOT_FOLDER_ID en el .env")
        sys.exit(1)

    print("Inicializando cliente de Google Drive…")
    adapter = GoogleDriveAdapter()
    repo = SupabaseGroupRepository()

    print("Cargando grupos desde Supabase…")
    # list_all() retorna raíces con .children poblados
    roots = repo.list_all()

    if not roots:
        print("No hay grupos en la BD. Nada que hacer.")
        return

    total = sum(1 + len(r.children) for r in roots)
    processed = 0

    for root in roots:
        # ── Nivel 1: carpeta raíz dentro de GOOGLE_DRIVE_ROOT_FOLDER_ID ──
        folder_id = adapter.ensure_folder(root.name, root_folder_id)

        if root.drive_folder_id != folder_id:
            root.drive_folder_id = folder_id
            repo.update(root)
            print(f"  [raíz] '{root.name}' → {folder_id}")
        else:
            print(f"  [raíz] '{root.name}' ya sincronizado ({folder_id})")

        processed += 1

        # ── Nivel 2: subcarpetas dentro de la carpeta raíz ────────────────
        for child in root.children:
            child_folder_id = adapter.ensure_folder(child.name, folder_id)

            if child.drive_folder_id != child_folder_id:
                child.drive_folder_id = child_folder_id
                repo.update(child)
                print(f"    [sub]  '{child.name}' → {child_folder_id}")
            else:
                print(f"    [sub]  '{child.name}' ya sincronizado ({child_folder_id})")

            processed += 1

    print(f"\n✓ Sincronización completa: {processed}/{total} grupos procesados.")


if __name__ == "__main__":
    sync()
