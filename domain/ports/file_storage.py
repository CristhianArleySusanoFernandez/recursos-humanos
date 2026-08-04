from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class UploadedFile:
    """Resultado que devuelve el adaptador tras subir un archivo."""
    file_id: str    # ID interno del proveedor de almacenamiento
    url: str        # URL pública o de visualización


class FileStorage(ABC):

    @abstractmethod
    def upload(
        self,
        file_content: bytes,
        file_name: str,
        mime_type: str,
        employee_name: str,
        group_drive_folder_id: str | None = None,
    ) -> UploadedFile:
        """
        Sube un archivo a la carpeta del empleado.
        La subcarpeta se crea usando employee_name como nombre.
        Si group_drive_folder_id está disponible se crea dentro de él,
        de lo contrario se crea dentro de GOOGLE_DRIVE_ROOT_FOLDER_ID.
        """

    @abstractmethod
    def delete(self, file_id: str) -> None:
        """Elimina un archivo por su ID de Drive."""

    @abstractmethod
    def get_url(self, file_id: str) -> str:
        """Construye la URL de visualización a partir del ID."""

    @abstractmethod
    def ensure_folder(self, folder_name: str, parent_folder_id: str) -> str:
        """
        Crea la carpeta folder_name dentro de parent_folder_id si no existe.
        Retorna el ID de la carpeta (nueva o existente).
        """
