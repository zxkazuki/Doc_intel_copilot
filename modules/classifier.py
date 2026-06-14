"""Document classification module — classifies documents via Amazon Bedrock."""

import logging
from dataclasses import dataclass
from enum import StrEnum

from config import get_settings
from infrastructure.bedrock_client import invoke_claude_json
from infrastructure.dynamodb_client import get_item, update_item
from infrastructure.s3_client import download_file
from prompts.classification import get_classification_prompts

logger = logging.getLogger(__name__)
settings = get_settings()

CONFIDENCE_THRESHOLD = 0.7

MEDIA_TYPE_MAP: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


class DocumentCategory(StrEnum):
    CONTRATO = "Contrato"
    LAUDO_MEDICO = "Laudo Médico"
    EXTRATO_BANCARIO = "Extrato Bancário"
    FICHA_CADASTRAL = "Ficha Cadastral"
    NOTA_FISCAL = "Nota Fiscal"
    DOCUMENTO_GENERICO = "Documento Genérico"


@dataclass
class ClassificationResult:
    category: DocumentCategory
    confidence: float
    success: bool
    error_message: str | None = None


def _resolve_media_type(file_format: str) -> str:
    """Resolve file format extension to MIME type."""
    return MEDIA_TYPE_MAP.get(file_format.lower(), "application/octet-stream")


def _parse_classification_response(response: dict | None) -> ClassificationResult | None:
    """Parse and validate Bedrock classification response. Returns None if invalid."""
    if response is None:
        return None

    category_str = response.get("category")
    confidence = response.get("confidence")

    if category_str is None or confidence is None:
        return None

    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        return None

    confidence = max(0.0, min(1.0, confidence))

    try:
        category = DocumentCategory(category_str)
    except ValueError:
        return None

    return ClassificationResult(category=category, confidence=confidence, success=True)


def _apply_confidence_fallback(result: ClassificationResult) -> ClassificationResult:
    """If confidence < 0.7 for a specific category, override to Documento Genérico."""
    if result.category != DocumentCategory.DOCUMENTO_GENERICO and result.confidence < CONFIDENCE_THRESHOLD:
        return ClassificationResult(
            category=DocumentCategory.DOCUMENTO_GENERICO,
            confidence=result.confidence,
            success=True,
        )
    return result


def classify_document(document_id: str) -> ClassificationResult:
    """Classify a document via Bedrock. Falls back to Documento Genérico if confidence < 0.7."""
    table_name = settings.dynamodb_documents_table

    # Fetch document record
    document = get_item(table_name, {"document_id": document_id})
    if document is None:
        return ClassificationResult(
            category=DocumentCategory.DOCUMENTO_GENERICO,
            confidence=0.0,
            success=False,
            error_message=f"Documento não encontrado: {document_id}",
        )

    s3_key = document.get("s3_key", "")
    file_format = document.get("file_format", "")

    # Download file from S3
    file_bytes = download_file(s3_key)
    if not file_bytes:
        update_item(table_name, {"document_id": document_id}, {"status": "classification_error"})
        return ClassificationResult(
            category=DocumentCategory.DOCUMENTO_GENERICO,
            confidence=0.0,
            success=False,
            error_message=f"Falha ao baixar arquivo do S3: {s3_key}",
        )

    # Invoke Bedrock for classification
    media_type = _resolve_media_type(file_format)
    system_prompt, user_prompt = get_classification_prompts()

    try:
        response = invoke_claude_json(
            prompt=user_prompt,
            system=system_prompt,
            file_bytes=file_bytes,
            media_type=media_type,
        )
    except Exception as e:
        logger.error("Erro na classificação do documento %s: %s", document_id, e)
        update_item(table_name, {"document_id": document_id}, {"status": "classification_error"})
        return ClassificationResult(
            category=DocumentCategory.DOCUMENTO_GENERICO,
            confidence=0.0,
            success=False,
            error_message=f"Erro ao invocar Bedrock: {e}",
        )

    # Parse and validate response
    parsed = _parse_classification_response(response)
    if parsed is None:
        update_item(table_name, {"document_id": document_id}, {"status": "classification_error"})
        return ClassificationResult(
            category=DocumentCategory.DOCUMENTO_GENERICO,
            confidence=0.0,
            success=False,
            error_message="Resposta inválida do modelo de classificação",
        )

    # Apply confidence fallback
    result = _apply_confidence_fallback(parsed)

    # Update DynamoDB with classification result
    update_item(
        table_name,
        {"document_id": document_id},
        {
            "category": str(result.category),
            "classification_confidence": str(result.confidence),
            "status": "classified",
        },
    )

    return result
