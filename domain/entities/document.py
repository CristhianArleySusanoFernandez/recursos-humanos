from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True)
class Document:
    id: UUID
    employee_id: UUID
    document_type_id: UUID
    file_name: str
    drive_file_id: str
    drive_url: str
    uploaded_at: datetime

    @classmethod
    def create(
        cls,
        employee_id: UUID,
        document_type_id: UUID,
        file_name: str,
        drive_file_id: str,
        drive_url: str,
    ) -> Document:
        return cls(
            id=uuid4(),
            employee_id=employee_id,
            document_type_id=document_type_id,
            file_name=file_name,
            drive_file_id=drive_file_id,
            drive_url=drive_url,
            uploaded_at=datetime.now(timezone.utc),
        )
