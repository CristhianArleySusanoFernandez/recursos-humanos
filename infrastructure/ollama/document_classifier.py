"""
Clasificador de documentos basado en Ollama (modelo local).

No requiere API key. Requiere que Ollama esté corriendo en
OLLAMA_BASE_URL (por defecto http://localhost:11434).

Los modelos de visión de Ollama aceptan imágenes PNG/JPEG, no PDFs.
Por eso la primera página de cada PDF se rasteriza a PNG con PyMuPDF
antes de enviarla al modelo.
"""

from __future__ import annotations

import base64
import os

import fitz  # PyMuPDF
import httpx

from domain.entities.document_type import EXTRA_CATEGORY, DocumentType
from domain.ports.document_classifier import DocumentClassifier
from domain.ports.document_type_repository import DocumentTypeRepository

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "gemma3:4b"
_TIMEOUT_SECONDS = 60.0
_PDF_RENDER_DPI = 150

_PDF_MIME = "application/pdf"

# Formatos que el modelo puede "ver" directamente.
_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


class OllamaDocumentClassifier(DocumentClassifier):

    def __init__(
        self,
        document_type_repo: DocumentTypeRepository,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._document_type_repo = document_type_repo
        self._base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        self._model = model or os.environ.get("OLLAMA_MODEL", _DEFAULT_MODEL)

    # ------------------------------------------------------------------
    # Puerto: DocumentClassifier
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Comprueba que Ollama responda. Nunca lanza excepción."""
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(f"{self._base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    def classify(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> DocumentType | None:
        """
        Pregunta a Ollama a qué tipo de documento corresponde el archivo.
        Retorna None si Ollama no responde, si agota el timeout, o si la
        respuesta no coincide con ningún código conocido.
        """
        doc_types = self._document_type_repo.list_active(
            exclude_category=EXTRA_CATEGORY
        )
        if not doc_types:
            return None

        by_code = {dt.code.upper(): dt for dt in doc_types}
        image_bytes = self._resolve_image(file_bytes, mime_type)

        prompt = self._build_prompt(
            filename,
            doc_types,
            use_vision=image_bytes is not None,
        )

        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        if image_bytes is not None:
            payload["images"] = [base64.b64encode(image_bytes).decode("ascii")]

        raw = self._generate(payload)
        if raw is None:
            return None

        return self._match_code(raw, by_code)

    # ------------------------------------------------------------------
    # Preparación de la imagen
    # ------------------------------------------------------------------

    def _resolve_image(self, file_bytes: bytes, mime_type: str) -> bytes | None:
        """
        Devuelve los bytes de imagen a enviar al modelo, o None si el archivo
        no es visualizable (p.ej. .docx) o si el PDF no se pudo rasterizar.
        En ese caso classify() cae a clasificación solo por nombre.
        """
        mime = (mime_type or "").lower()

        if mime in _IMAGE_MIME_TYPES:
            return file_bytes

        if mime == _PDF_MIME:
            return self._pdf_to_image(file_bytes)

        return None

    @staticmethod
    def _pdf_to_image(file_bytes: bytes) -> bytes | None:
        """
        Rasteriza la primera página del PDF a PNG a 150 DPI.
        Retorna None si el PDF está corrupto, cifrado o vacío.
        """
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                if doc.page_count == 0:
                    return None
                page = doc.load_page(0)
                pixmap = page.get_pixmap(dpi=_PDF_RENDER_DPI)
                return pixmap.tobytes("png")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Llamada a Ollama
    # ------------------------------------------------------------------

    def _generate(self, payload: dict) -> str | None:
        """Llama a /api/generate. Retorna el texto o None ante cualquier fallo."""
        try:
            with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
                response = client.post(f"{self._base_url}/api/generate", json=payload)
            if response.status_code != 200:
                return None
            return (response.json().get("response") or "").strip()
        except Exception:
            # Timeout, conexión rechazada, JSON inválido: se degrada a None.
            return None

    def _build_prompt(
        self,
        filename: str,
        doc_types: list[DocumentType],
        use_vision: bool,
    ) -> str:
        catalog = "\n".join(
            f"- {dt.code}: {dt.name} ({dt.category})" for dt in doc_types
        )
        source = (
            "Analiza el contenido de la imagen adjunta y el nombre del archivo."
            if use_vision
            else "Analiza ÚNICAMENTE el nombre del archivo (el contenido no está disponible)."
        )
        return (
            "Eres un clasificador de documentos de recursos humanos de una empresa "
            "colombiana.\n\n"
            f"{source}\n\n"
            f"Nombre del archivo: {filename}\n\n"
            "Categorías disponibles (código: descripción):\n"
            f"{catalog}\n\n"
            "Responde ÚNICAMENTE con el código exacto de la categoría que corresponde. "
            "Sin explicación, sin puntuación, sin comillas, sin texto adicional.\n"
            "Si el archivo no corresponde con ninguna categoría, responde exactamente: NINGUNA"
        )

    @staticmethod
    def _match_code(raw: str, by_code: dict[str, DocumentType]) -> DocumentType | None:
        """Extrae un código válido de la respuesta del modelo."""
        cleaned = raw.strip().strip("`\"'.,:;").upper()

        if cleaned in by_code:
            return by_code[cleaned]

        # El modelo a veces devuelve una frase; busca un código dentro del texto.
        # Se prioriza el código más largo para evitar falsos positivos
        # (ej: "RUT" dentro de "RUT_LICENCIA").
        for code in sorted(by_code, key=len, reverse=True):
            if code in cleaned:
                return by_code[code]

        return None
