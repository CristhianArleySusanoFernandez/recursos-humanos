import os
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from domain.entities.group import Group
from domain.exceptions import GroupNotFoundError
from domain.ports.file_storage import FileStorage
from domain.ports.group_repository import GroupRepository


@dataclass
class CreateGroupInput:
    name: str
    parent_id: UUID | None = None


class CreateGroup:

    def __init__(
        self,
        group_repo: GroupRepository,
        file_storage: FileStorage,
    ) -> None:
        self._group_repo = group_repo
        self._file_storage = file_storage

    def execute(self, input: CreateGroupInput) -> None:
        parent = None
        if input.parent_id is not None:
            parent = self._group_repo.get_by_id(input.parent_id)
            if parent is None:
                raise GroupNotFoundError(input.parent_id)
            if not parent.is_root():
                raise ValueError(
                    f"El grupo '{parent.name}' ya es un subgrupo (nivel 2). "
                    "No se permiten más de 2 niveles de jerarquía."
                )

        group = Group(
            id=uuid4(),
            name=input.name.strip(),
            parent_id=input.parent_id,
            drive_folder_id=None,
            created_at=datetime.now(timezone.utc),
        )
        self._group_repo.save(group)

        # Crear carpeta en Drive y persistir su ID
        try:
            if input.parent_id is None:
                # Grupo raíz → carpeta dentro de la raíz de Drive
                root_folder_id = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
                if not root_folder_id:
                    raise ValueError("GOOGLE_DRIVE_ROOT_FOLDER_ID no está configurado.")
                parent_folder_id = root_folder_id
            else:
                # Subgrupo → carpeta dentro de la carpeta del padre
                if not parent or not parent.drive_folder_id:
                    raise ValueError(
                        f"El grupo padre '{parent.name if parent else input.parent_id}' "
                        "no tiene drive_folder_id. Ejecuta sync_drive_folders.py primero."
                    )
                parent_folder_id = parent.drive_folder_id

            folder_id = self._file_storage.ensure_folder(group.name, parent_folder_id)
            group.drive_folder_id = folder_id
            self._group_repo.update(group)
        except Exception:
            # Fallo de Drive no impide que el grupo exista en BD
            pass
