# Re-exporta las entidades para facilitar imports desde domain.entities.
from .document_type import DocumentType
from .document import Document
from .employee import Employee

__all__ = ["DocumentType", "Document", "Employee"]
