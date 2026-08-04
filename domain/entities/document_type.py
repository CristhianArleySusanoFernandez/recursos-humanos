from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

# Categoría de los tipos auto-generados por la subida masiva para archivos
# que el clasificador no supo encajar. No son documentos requeridos: quedan
# fuera del checklist y del ratio de completitud.
EXTRA_CATEGORY = "EXTRA"


@dataclass
class DocumentType:
    id: UUID
    name: str
    code: str
    category: str       # 'INGRESO' | 'RETIRO' | 'EXTRA'
    is_active: bool
    order_index: int
    created_at: datetime
