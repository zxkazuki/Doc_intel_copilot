import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from config import get_settings
from infrastructure.dynamodb_client import put_item
from infrastructure.s3_client import upload_file

logger = logging.getLogger(__name__)

CONTENT_TYPE_MAP: dict[str, str] = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


@dataclass
class ValidationResult:
    valid: bool
    error_message: str | None = None


@dataclass
class UploadResult:
    success: bool
    document_id: str | None = None
    error_message: str | None = None


def validate_file(file_name: str, file_size_bytes: int) -> ValidationResult:
    """Valida formato e tamanho. Retorna erro descritivo se inválido."""
    settings = get_settings()
    allowed_formats = settings.allowed_formats
    max_size_bytes = settings.max_file_size_mb * 1024 * 1024

    extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

    if extension not in allowed_formats:
        formats_display = ", ".join(fmt.upper() for fmt in allowed_formats)
        return ValidationResult(
            valid=False,
            error_message=f"Formato não suportado. Formatos aceitos: {formats_display}",
        )

    if file_size_bytes > max_size_bytes:
        return ValidationResult(
            valid=False,
            error_message=f"Arquivo excede o tamanho máximo de {settings.max_file_size_mb} MB",
        )

    return ValidationResult(valid=True)


def upload_document(file_bytes: bytes, file_name: str, file_size_bytes: int) -> UploadResult:
    """Valida, armazena no S3, registra metadados no DynamoDB."""
    settings = get_settings()

    validation = validate_file(file_name, file_size_bytes)
    if not validation.valid:
        return UploadResult(success=False, error_message=validation.error_message)

    document_id = str(uuid.uuid4())
    extension = file_name.rsplit(".", 1)[-1].lower()
    s3_key = f"documents/{document_id}.{extension}"
    content_type = CONTENT_TYPE_MAP.get(extension, "application/octet-stream")

    if not upload_file(file_bytes, s3_key, content_type):
        return UploadResult(
            success=False,
            error_message="Falha ao enviar arquivo. Tente novamente.",
        )

    try:
        put_item(settings.dynamodb_documents_table, {
            "document_id": document_id,
            "file_name": file_name,
            "file_format": extension,
            "file_size_bytes": file_size_bytes,
            "s3_key": s3_key,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "uploaded",
        })
    except Exception as e:
        logger.error("Erro ao registrar documento no DynamoDB: %s", e)
        return UploadResult(
            success=False,
            error_message="Falha ao registrar documento. Tente novamente.",
        )

    return UploadResult(success=True, document_id=document_id)
