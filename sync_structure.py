"""
sync_structure.py
=================
Sincroniza la estructura de grupos desde el Drive ORIGINAL (carpeta PERSONAL)
hacia Supabase y hacia la carpeta de la app (PersonalDST-APP).

Qué hace:
  1. Lee las carpetas de zona del Drive original (solo lectura).
  2. Procesa únicamente las zonas de interés:
         TUNJA, BARBOSA, CHIQUINQUIRA, ESTUDIANTES, RETIRADOS
     (ignora CANDIDATOS, CLARO, NOMINA, etc.).
  3. Normaliza todos los nombres: MAYÚSCULAS, sin tildes, sin espacios
     sobrantes (Ñ se conserva). Ej: "Logísticos" → "LOGISTICOS".
  4. Limpia groups (y employees) en Supabase y los recrea a partir de las
     carpetas reales del Drive.
  5. Crea las carpetas equivalentes en PersonalDST-APP y guarda el
     drive_folder_id de cada una en Supabase.

SEGURIDAD:
  - NO toca ningún archivo dentro de las carpetas de empleados.
  - Solo LEE la estructura de carpetas del origen.
  - Solo CREA carpetas (vacías) en el destino.
  - Pide confirmación antes de borrar y recrear los grupos.

Variables de entorno (.env):
  GOOGLE_DRIVE_SOURCE_FOLDER_ID  → carpeta PERSONAL (origen, solo lectura)
  GOOGLE_DRIVE_ROOT_FOLDER_ID    → carpeta PersonalDST-APP (destino)

Uso:
    python sync_structure.py
"""

from __future__ import annotations

import os
import sys
import unicodedata
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Infraestructura del proyecto (tras cargar .env)
# ---------------------------------------------------------------------------
from infrastructure.google_drive.drive_adapter import _build_service
from infrastructure.supabase.client import get_supabase_client

_FOLDER_MIME = "application/vnd.google-apps.folder"

# Zonas que sí nos interesan (comparadas ya normalizadas).
ZONAS_DE_INTERES: set[str] = {
    "TUNJA", "BARBOSA", "CHIQUINQUIRA", "ESTUDIANTES", "RETIRADOS",
}


# ---------------------------------------------------------------------------
# Normalización de nombres
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """
    MAYÚSCULAS, sin tildes, sin espacios sobrantes. La Ñ se conserva.
    Ej: "  Logísticos " → "LOGISTICOS"; "Chiquinquirá" → "CHIQUINQUIRA".
    """
    # Proteger la Ñ antes de descomponer los acentos.
    protected = text.replace("ñ", "\0").replace("Ñ", "\0")
    nfkd = unicodedata.normalize("NFKD", protected)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.replace("\0", "Ñ").strip().upper()


# ---------------------------------------------------------------------------
# Lectura del Drive origen
# ---------------------------------------------------------------------------

def list_subfolders(service, parent_id: str) -> list[dict]:
    """Lista las subcarpetas directas de parent_id (solo lectura)."""
    results: list[dict] = []
    page_token = None
    while True:
        kwargs = dict(
            q=(
                f"'{parent_id}' in parents "
                f"and mimeType='{_FOLDER_MIME}' "
                f"and trashed=false"
            ),
            fields="nextPageToken, files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=1000,
            orderBy="name",
        )
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.files().list(**kwargs).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def ensure_folder(service, name: str, parent_id: str) -> str:
    """Crea la carpeta (si no existe) dentro de parent_id y retorna su ID."""
    safe = name.replace("'", "\\'")
    query = (
        f"name='{safe}' and '{parent_id}' in parents "
        f"and mimeType='{_FOLDER_MIME}' and trashed=false"
    )
    resp = service.files().list(
        q=query,
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]

    folder = service.files().create(
        body={"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]},
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return folder["id"]


# ---------------------------------------------------------------------------
# Sincronizador
# ---------------------------------------------------------------------------

class StructureSync:
    def __init__(self) -> None:
        self.db = get_supabase_client()
        self.service = _build_service()
        self.source_id = os.environ.get("GOOGLE_DRIVE_SOURCE_FOLDER_ID", "")
        self.dest_id = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
        # Resumen: zona normalizada → lista de subgrupos normalizados
        self.summary: list[tuple[str, list[str]]] = []

    # ------------------------------------------------------------------
    # Supabase
    # ------------------------------------------------------------------

    def wipe_groups(self) -> None:
        """Borra todos los empleados y grupos existentes."""
        # employees primero (FK RESTRICT hacia groups).
        self.db.table("employees").delete().neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()
        self.db.table("groups").delete().neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()
        print("  Empleados y grupos existentes eliminados.")

    def insert_group(self, name: str, parent_id: str | None, drive_folder_id: str) -> str:
        gid = str(uuid4())
        self.db.table("groups").insert({
            "id": gid,
            "name": name,
            "parent_id": parent_id,
            "drive_folder_id": drive_folder_id,
        }).execute()
        return gid

    # ------------------------------------------------------------------
    # Proceso principal
    # ------------------------------------------------------------------

    def run(self) -> None:
        if not self.source_id:
            print("✗ Falta GOOGLE_DRIVE_SOURCE_FOLDER_ID en .env")
            sys.exit(1)
        if not self.dest_id:
            print("✗ Falta GOOGLE_DRIVE_ROOT_FOLDER_ID en .env")
            sys.exit(1)

        print(f"\nOrigen  (PERSONAL):        {self.source_id}")
        print(f"Destino (PersonalDST-APP): {self.dest_id}\n")

        # 1. Leer zonas del origen y filtrar las de interés.
        zona_folders = list_subfolders(self.service, self.source_id)
        zonas = [z for z in zona_folders if normalize(z["name"]) in ZONAS_DE_INTERES]

        if not zonas:
            print("✗ No se encontró ninguna zona de interés en el origen.")
            sys.exit(1)

        print("Zonas de interés encontradas:",
              [normalize(z["name"]) for z in zonas], "\n")

        # 2. Limpiar Supabase.
        self.wipe_groups()

        # 3. Recrear cada zona con sus subgrupos.
        for zona in zonas:
            self._process_zona(zona)

        self._print_summary()

    def _process_zona(self, zona: dict) -> None:
        zona_norm = normalize(zona["name"])
        print(f"\nZona: {zona_norm}")

        # Carpeta de la zona en el destino.
        dest_zona_id = ensure_folder(self.service, zona_norm, self.dest_id)
        # Grupo nivel 1 en Supabase.
        zona_group_id = self.insert_group(zona_norm, None, dest_zona_id)

        # Subcarpetas reales de la zona en el origen.
        sub_folders = list_subfolders(self.service, zona["id"])
        subgrupos: list[str] = []

        for sub in sub_folders:
            sub_norm = normalize(sub["name"])
            # RETIRADOS: "RetiradosBarbosa" / "RETIRADOS_BARBOSA" → "BARBOSA"
            if zona_norm == "RETIRADOS":
                sub_norm = self._clean_retirado_name(sub_norm)
            if not sub_norm:
                continue

            dest_sub_id = ensure_folder(self.service, sub_norm, dest_zona_id)
            self.insert_group(sub_norm, zona_group_id, dest_sub_id)
            subgrupos.append(sub_norm)
            print(f"  → {sub_norm}")

        self.summary.append((zona_norm, subgrupos))

    @staticmethod
    def _clean_retirado_name(sub_norm: str) -> str:
        """
        Quita el prefijo RETIRADOS del nombre del subgrupo.
        "RETIRADOS_BARBOSA" → "BARBOSA"; "RETIRADOSBARBOSA" → "BARBOSA".
        """
        for prefix in ("RETIRADOS_", "RETIRADOS", "RETIRADO_", "RETIRADO"):
            if sub_norm.startswith(prefix) and len(sub_norm) > len(prefix):
                return sub_norm[len(prefix):].strip("_ ").strip()
        return sub_norm

    # ------------------------------------------------------------------
    # Resumen
    # ------------------------------------------------------------------

    def _print_summary(self) -> None:
        print(f"\n{'='*50}")
        print("RESUMEN")
        print(f"{'='*50}")
        total_sub = 0
        for zona, subgrupos in self.summary:
            print(f"\nZONA: {zona}")
            for s in subgrupos:
                print(f"  → {s}")
            total_sub += len(subgrupos)
        print(f"\nTotal: {len(self.summary)} zonas, {total_sub} subgrupos creados")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  Sincronización de estructura Drive → Supabase")
    print("  Distribuciones SantiagoDeTunja S.A.S.")
    print("=" * 60)
    confirm = input(
        "\nSe van a eliminar todos los grupos existentes y recrearlos "
        "desde el Drive. ¿Continuar? (s/n): "
    ).strip().lower()
    if confirm != "s":
        print("Operación cancelada.")
        sys.exit(0)

    StructureSync().run()
