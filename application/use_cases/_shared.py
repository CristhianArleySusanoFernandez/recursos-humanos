"""
Utilidades compartidas entre casos de uso.
"""
from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime, timezone
from uuid import UUID, uuid4

from domain.entities.document_type import EXTRA_CATEGORY, DocumentType
from domain.ports.document_type_repository import DocumentTypeRepository

# Valor centinela que envían los <select> del frontend cuando el usuario elige
# "marcar como Extra" en lugar de un tipo concreto (un UUID). Los endpoints lo
# detectan y lo resuelven a un tipo EXTRA autogenerado con get_or_create_extra_type.
EXTRA_AUTO_SENTINEL = "EXTRA_AUTO"


def normalize_name_key(name: str) -> str:
    """
    Clave de orden alfabético insensible a mayúsculas y tildes.
    (NFKD + quita diacríticos + minúsculas.)
    """
    nfkd = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).strip().lower()


def get_or_create_extra_type(
    document_type_repo: DocumentTypeRepository, filename: str
) -> UUID:
    """
    Devuelve el id de un tipo EXTRA propio del archivo (uno por nombre de
    archivo), creándolo si no existe. Así cada documento marcado como Extra
    tiene su propio tipo y no colisiona con otros (UNIQUE employee_id+type).

    code = "EXTRA_" + primeros 8 chars del MD5 del filename (en mayúsculas,
    para coincidir con get_by_code, que normaliza a upper).
    """
    digest = hashlib.md5(filename.encode("utf-8")).hexdigest()[:8]
    code = ("EXTRA_" + digest).upper()

    existing = document_type_repo.get_by_code(code)
    if existing is not None:
        return existing.id

    new_type = DocumentType(
        id=uuid4(),
        name=filename[:100],
        code=code,
        category=EXTRA_CATEGORY,
        is_active=True,
        order_index=99,
        created_at=datetime.now(timezone.utc),
    )
    document_type_repo.save(new_type)
    return new_type.id
