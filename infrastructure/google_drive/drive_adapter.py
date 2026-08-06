import io
import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from domain.ports.file_storage import FileStorage, UploadedFile

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_FOLDER_MIME = "application/vnd.google-apps.folder"
_VIEW_URL = "https://drive.google.com/file/d/{file_id}/view"


def _load_oauth_credentials() -> tuple[Credentials, str | None, str]:
    """
    Carga las credenciales OAuth del usuario admitiendo dos modos:

      - Variable de entorno GOOGLE_OAUTH_TOKEN_JSON: contenido completo del
        token.json como string. Útil para servidores efímeros sin sistema de
        archivos persistente. En este modo NO se escribe a disco.
      - Archivo GOOGLE_OAUTH_TOKEN_PATH (comportamiento local actual).

    La variable de entorno tiene prioridad si está presente.

    Devuelve (creds, persist_path, source):
      - persist_path: ruta donde reguardar el token tras un refresh, o None
        cuando se usa la variable de entorno (no hay dónde persistir).
      - source: descripción del origen para los mensajes de error.
    """
    token_json = os.environ.get("GOOGLE_OAUTH_TOKEN_JSON", "").strip()
    if token_json:
        info = json.loads(token_json)
        creds = Credentials.from_authorized_user_info(info, _SCOPES)
        return creds, None, "GOOGLE_OAUTH_TOKEN_JSON"

    token_path = os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", "")
    if not token_path:
        raise RuntimeError(
            "Falta la configuración del token OAuth. Define GOOGLE_OAUTH_TOKEN_PATH "
            "(ruta al archivo token.json) o GOOGLE_OAUTH_TOKEN_JSON (contenido del "
            "token como variable de entorno) en tu .env."
        )

    if not os.path.exists(token_path):
        raise RuntimeError(
            f"No se encontró el archivo de token OAuth en: {token_path}\n"
            "Ejecuta primero el script de autorización:\n"
            "    python setup_google_auth.py"
        )

    creds = Credentials.from_authorized_user_file(token_path, _SCOPES)
    return creds, token_path, token_path


def _build_service():
    """
    Construye el cliente autenticado de Google Drive usando OAuth 2.0.

    El token se carga desde GOOGLE_OAUTH_TOKEN_JSON (variable de entorno) o desde
    GOOGLE_OAUTH_TOKEN_PATH (archivo local); se refresca si está vencido. En modo
    variable de entorno el token renovado NO se persiste (el refresh token sigue
    siendo válido y el access token se regenera en cada arranque sin problema).
    """
    # [PERF-DEBUG] marca cuándo se AUTENTICA realmente contra Drive (costoso).
    print("[PERF]   >>> _build_service(): AUTENTICANDO contra Google Drive <<<", flush=True)
    creds, persist_path, source = _load_oauth_credentials()

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Solo se reguarda en modo archivo; en modo variable de entorno no hay
            # sistema de archivos persistente donde escribir (y no hace falta).
            if persist_path:
                with open(persist_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
        else:
            raise RuntimeError(
                f"El token OAuth ({source}) no es válido y no puede refrescarse.\n"
                "Vuelve a ejecutar el script de autorización:\n"
                "    python setup_google_auth.py"
            )

    return build("drive", "v3", credentials=creds, cache_discovery=False)


class GoogleDriveAdapter(FileStorage):
    """
    Almacena archivos en Google Drive usando OAuth 2.0 con credenciales de usuario.

    Estructura de carpetas:
        <GOOGLE_DRIVE_ROOT_FOLDER_ID>/
            [<group_drive_folder_id>/]   ← carpeta del grupo, si está configurada
                <employee_name>/         ← una carpeta por empleado
                    documento.pdf

    La conexión a Drive es lazy: se establece la primera vez que se necesita,
    no en __init__. Esto permite instanciar el adaptador sin token OAuth
    (útil cuando la operación no requiere Drive, ej: desactivar sin carpeta).
    """

    def __init__(self) -> None:
        # [PERF-DEBUG] marca cada vez que se INSTANCIA el adaptador (barato, lazy).
        print("[PERF]   GoogleDriveAdapter() instanciado (aún sin autenticar)", flush=True)
        self._root_folder_id = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
        self._service = None  # lazy — se inicializa en _get_service()

    def _get_service(self):
        if self._service is None:
            if not self._root_folder_id:
                raise RuntimeError("Falta la variable de entorno GOOGLE_DRIVE_ROOT_FOLDER_ID.")
            self._service = _build_service()
        return self._service

    # ------------------------------------------------------------------
    # Puerto: FileStorage
    # ------------------------------------------------------------------

    def upload(
        self,
        file_content: bytes,
        file_name: str,
        mime_type: str,
        employee_name: str,
        group_drive_folder_id: str | None = None,
    ) -> UploadedFile:
        """
        Sube el archivo a la subcarpeta del empleado.
        La subcarpeta se crea dentro de group_drive_folder_id si está disponible,
        o dentro de GOOGLE_DRIVE_ROOT_FOLDER_ID en caso contrario.
        """
        parent_folder = group_drive_folder_id or self._root_folder_id
        target_folder = self._get_or_create_folder(employee_name, parent_folder)

        metadata = {
            "name": file_name,
            "parents": [target_folder],
        }
        media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype=mime_type, resumable=False)

        file = (
            self._get_service().files()
            .create(
                body=metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            )
            .execute()
        )
        file_id: str = file["id"]

        # Permiso de lectura pública para que la URL funcione sin autenticación adicional.
        self._get_service().permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()

        return UploadedFile(file_id=file_id, url=self.get_url(file_id))

    def delete(self, file_id: str) -> None:
        """Elimina el archivo de Drive. No lanza excepción si ya no existe (idempotente)."""
        try:
            self._get_service().files().delete(
                fileId=file_id,
                supportsAllDrives=True,
            ).execute()
        except Exception:
            pass

    def get_url(self, file_id: str) -> str:
        return _VIEW_URL.format(file_id=file_id)

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def move_folder(
        self,
        folder_name: str,
        from_parent_id: str,
        to_parent_id: str,
    ) -> None:
        """
        Mueve la carpeta con ese nombre desde from_parent_id a to_parent_id.
        No lanza excepción si la carpeta no existe (puede que nunca se haya subido
        ningún archivo para ese empleado).
        """
        folder_id = self._find_folder(folder_name, from_parent_id)
        if folder_id is None:
            return
        self._get_service().files().update(
            fileId=folder_id,
            addParents=to_parent_id,
            removeParents=from_parent_id,
            fields="id, parents",
            supportsAllDrives=True,
        ).execute()

    def ensure_folder(self, folder_name: str, parent_folder_id: str) -> str:
        """Crea la carpeta si no existe y retorna su ID."""
        return self._get_or_create_folder(folder_name, parent_folder_id)

    def _get_or_create_folder(self, folder_name: str, parent_id: str) -> str:
        """
        Retorna el ID de una subcarpeta con ese nombre dentro de parent_id.
        La crea si no existe.
        """
        existing_id = self._find_folder(folder_name, parent_id)
        if existing_id:
            return existing_id

        metadata = {
            "name": folder_name,
            "mimeType": _FOLDER_MIME,
            "parents": [parent_id],
        }
        folder = (
            self._get_service().files()
            .create(body=metadata, fields="id", supportsAllDrives=True)
            .execute()
        )
        return folder["id"]

    def _find_folder(self, name: str, parent_id: str) -> str | None:
        """Busca una carpeta por nombre dentro de parent_id. Retorna su ID o None."""
        safe_name = name.replace("'", "\\'")
        query = (
            f"name='{safe_name}' "
            f"and '{parent_id}' in parents "
            f"and mimeType='{_FOLDER_MIME}' "
            f"and trashed=false"
        )
        response = (
            self._get_service().files()
            .list(
                q=query,
                fields="files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files = response.get("files", [])
        return files[0]["id"] if files else None
