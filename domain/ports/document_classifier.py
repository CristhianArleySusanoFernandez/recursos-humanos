from abc import ABC, abstractmethod

from domain.entities.document_type import DocumentType


class DocumentClassifier(ABC):
    """
    Puerto para clasificar automáticamente un archivo en uno de los
    tipos de documento configurados en el sistema.

    Las implementaciones NO deben lanzar excepciones por fallos del motor
    de clasificación (timeout, servicio caído, respuesta inválida):
    en esos casos retornan None y el caso de uso decide qué hacer.
    """

    @abstractmethod
    def classify(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> DocumentType | None:
        """
        Retorna el DocumentType al que corresponde el archivo,
        o None si no se pudo determinar.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Retorna True si el motor de clasificación está operativo."""
