"""Structured field extraction module — extracts key-value fields from documents using Bedrock."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from config import get_settings
from infrastructure.bedrock_client import invoke_claude_json
from infrastructure.dynamodb_client import get_item, put_item, update_item
from infrastructure.s3_client import download_file
from prompts.extraction import (
    EXTRACTION_SCHEMAS,
    get_extraction_prompt,
    get_extraction_system_prompt,
)

logger = logging.getLogger(__name__)

__all__ = ["ExtractedField", "ExtractionResult", "EXTRACTION_SCHEMAS", "extract_fields"]


@dataclass
class ExtractedField:
    name: str
    value: str | None
    confidence: float


@dataclass
class ExtractionResult:
    document_id: str
    fields: list[ExtractedField]
    success: bool
    error_message: str | None = None


_FORMAT_TO_MEDIA_TYPE: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


def _get_media_type(file_format: str) -> str:
    return _FORMAT_TO_MEDIA_TYPE.get(file_format.lower(), "application/octet-stream")


def _clamp_confidence(raw: object) -> float:
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.0


def _parse_extraction_response(response: dict, category: str) -> list[ExtractedField]:
    """Parse Bedrock JSON response into ExtractedField list with schema enforcement."""
    raw_fields = response.get("fields", [])

    fields = [
        ExtractedField(
            name=raw.get("name", ""),
            value=raw.get("value"),
            confidence=_clamp_confidence(raw.get("confidence", 0.0)),
        )
        for raw in raw_fields
        if isinstance(raw, dict)
    ]

    if category == "Documento Genérico":
        fields = fields[:10]
    else:
        # Ensure ALL schema-defined fields are present
        existing_names = {f.name for f in fields}
        for field_name in EXTRACTION_SCHEMAS.get(category, []):
            if field_name not in existing_names:
                fields.append(ExtractedField(name=field_name, value=None, confidence=0.0))

    # Invariant: null value → confidence must be 0.0
    for field in fields:
        if field.value is None:
            field.confidence = 0.0

    return fields


def _set_error_status(document_id: str) -> None:
    settings = get_settings()
    try:
        update_item(
            settings.dynamodb_documents_table,
            {"document_id": document_id},
            {"status": "extraction_error"},
        )
    except Exception as e:
        logger.error("Erro ao atualizar status de erro: %s", e)


def _error_result(document_id: str, message: str) -> ExtractionResult:
    return ExtractionResult(document_id=document_id, fields=[], success=False, error_message=message)


def extract_fields(document_id: str) -> ExtractionResult:
    """Extract structured fields from a document based on its category.

    1. Fetch document record from DynamoDB
    2. Download file from S3
    3. Invoke Bedrock with category-specific prompt
    4. Parse, validate, and persist extraction result
    """
    settings = get_settings()

    # Fetch document record
    document = get_item(settings.dynamodb_documents_table, {"document_id": document_id})
    if not document:
        return _error_result(document_id, "Documento não encontrado")

    category = document.get("category", "")
    s3_key = document.get("s3_key", "")
    file_format = document.get("file_format", "")

    if not category or not s3_key:
        _set_error_status(document_id)
        return _error_result(document_id, "Documento sem categoria ou s3_key")

    # Download file
    file_bytes = download_file(s3_key)
    if not file_bytes:
        _set_error_status(document_id)
        return _error_result(document_id, "Falha ao baixar arquivo do S3")

    # Get prompts
    try:
        system_prompt = get_extraction_system_prompt()
        user_prompt = get_extraction_prompt(category)
    except ValueError as e:
        _set_error_status(document_id)
        return _error_result(document_id, str(e))

    # Invoke Bedrock
    try:
        response = invoke_claude_json(
            prompt=user_prompt,
            system=system_prompt,
            file_bytes=file_bytes,
            media_type=_get_media_type(file_format),
        )
    except Exception as e:
        logger.error("Erro ao invocar Bedrock para extração: %s", e)
        _set_error_status(document_id)
        return _error_result(document_id, f"Erro na extração: {e}")

    # invoke_claude_json returns None when retry exhausted (timeout/connection)
    if response is None:
        _set_error_status(document_id)
        return _error_result(document_id, "Timeout ou falha de conexão com Bedrock")

    # Parse response
    fields = _parse_extraction_response(response, category)

    # Persist extraction result
    extracted_at = datetime.now(timezone.utc).isoformat()
    fields_as_dicts = [
        {"name": f.name, "value": f.value, "confidence": str(f.confidence)}
        for f in fields
    ]

    try:
        put_item(
            settings.dynamodb_extractions_table,
            {
                "document_id": document_id,
                "fields": fields_as_dicts,
                "extracted_at": extracted_at,
            },
        )
        update_item(
            settings.dynamodb_documents_table,
            {"document_id": document_id},
            {"status": "extracted"},
        )
    except Exception as e:
        logger.error("Erro ao salvar extração no DynamoDB: %s", e)
        _set_error_status(document_id)
        return _error_result(document_id, f"Erro ao persistir extração: {e}")

    return ExtractionResult(document_id=document_id, fields=fields, success=True)
