"""Review module — human-in-the-loop approval, rejection, and field corrections."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from botocore.exceptions import ClientError

from config import get_settings
from infrastructure.dynamodb_client import put_item, update_item

logger = logging.getLogger(__name__)
settings = get_settings()


class ReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    CORRECTION = "correction"


@dataclass
class FieldCorrection:
    field_name: str
    original_value: str | None
    corrected_value: str


@dataclass
class ReviewEntry:
    reviewer_id: str
    timestamp: datetime
    action: ReviewAction
    field_name: str | None = None
    original_value: str | None = None
    new_value: str | None = None


def approve_document(document_id: str, reviewer_id: str) -> bool:
    """Atualiza status para 'approved' e registra no histórico de revisões."""
    try:
        update_item(
            table_name=settings.dynamodb_documents_table,
            key={"document_id": document_id},
            updates={"status": "approved"},
        )
        put_item(
            table_name=settings.dynamodb_reviews_table,
            item={
                "review_id": str(uuid.uuid4()),
                "document_id": document_id,
                "reviewer_id": reviewer_id,
                "action": ReviewAction.APPROVE,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        return True
    except ClientError as e:
        logger.error("Erro ao aprovar documento %s: %s", document_id, e)
        return False


def reject_document(document_id: str, reviewer_id: str) -> bool:
    """Atualiza status para 'rejected' e registra no histórico de revisões."""
    try:
        update_item(
            table_name=settings.dynamodb_documents_table,
            key={"document_id": document_id},
            updates={"status": "rejected"},
        )
        put_item(
            table_name=settings.dynamodb_reviews_table,
            item={
                "review_id": str(uuid.uuid4()),
                "document_id": document_id,
                "reviewer_id": reviewer_id,
                "action": ReviewAction.REJECT,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        return True
    except ClientError as e:
        logger.error("Erro ao rejeitar documento %s: %s", document_id, e)
        return False


def correct_field(
    document_id: str, reviewer_id: str, correction: FieldCorrection
) -> bool:
    """Registra correção de campo individual no histórico (não altera status)."""
    try:
        put_item(
            table_name=settings.dynamodb_reviews_table,
            item={
                "review_id": str(uuid.uuid4()),
                "document_id": document_id,
                "reviewer_id": reviewer_id,
                "action": ReviewAction.CORRECTION,
                "field_name": correction.field_name,
                "original_value": correction.original_value,
                "new_value": correction.corrected_value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        return True
    except ClientError as e:
        logger.error(
            "Erro ao registrar correção do campo '%s' no documento %s: %s",
            correction.field_name,
            document_id,
            e,
        )
        return False
