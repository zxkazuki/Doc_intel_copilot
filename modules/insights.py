"""Insight generation module — analyzes extractions to produce business insights."""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from config import get_settings
from infrastructure.bedrock_client import invoke_claude_json
from infrastructure.dynamodb_client import get_item, put_item, update_item
from prompts.insights import format_insights_user_prompt, get_insights_system_prompt

logger = logging.getLogger(__name__)

SEVERITY_ORDER: dict[str, int] = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


class InsightSeverity(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class InsightCategory(StrEnum):
    COMPLIANCE = "Compliance"
    QUALIDADE = "Qualidade"
    FINANCEIRO = "Financeiro"
    OPERACIONAL = "Operacional"


@dataclass
class Insight:
    title: str           # max 100 chars
    description: str     # max 500 chars
    category: InsightCategory
    severity: InsightSeverity


@dataclass
class InsightsResult:
    document_id: str
    insights: list[Insight]
    success: bool
    error_message: str | None = None


def _try_parse_insight(raw: dict) -> Insight | None:
    """Parse a single raw dict into an Insight, returning None if invalid."""
    try:
        category = InsightCategory(str(raw.get("category", "")))
        severity = InsightSeverity(str(raw.get("severity", "")))
    except ValueError:
        return None

    return Insight(
        title=str(raw.get("title", ""))[:100],
        description=str(raw.get("description", ""))[:500],
        category=category,
        severity=severity,
    )


def _parse_insights(raw_list: list[dict]) -> list[Insight]:
    """Parse raw insights, enforcing max 20 and filtering invalid entries."""
    parsed = [_try_parse_insight(r) for r in raw_list[:20]]
    return [i for i in parsed if i is not None]


def calculate_max_severity(insights: list[Insight]) -> str:
    """Return the highest severity value from a list of insights."""
    if not insights:
        return InsightSeverity.LOW.value
    return max(insights, key=lambda i: SEVERITY_ORDER[i.severity.value]).severity.value


DEFAULT_INSIGHT = Insight(
    title="Documento processado sem inconsistências detectadas",
    description="A análise não identificou problemas ou inconsistências no documento.",
    category=InsightCategory.OPERACIONAL,
    severity=InsightSeverity.LOW,
)


def _set_error_status(document_id: str) -> None:
    """Attempt to set document status to insights_error."""
    settings = get_settings()
    try:
        update_item(
            settings.dynamodb_documents_table,
            {"document_id": document_id},
            {"status": "insights_error"},
        )
    except Exception as e:
        logger.error("Erro ao atualizar status de erro: %s", e)


def generate_insights(document_id: str) -> InsightsResult:
    """Analyze extraction to generate insights and detect inconsistencies."""
    settings = get_settings()

    try:
        return _execute_insights_pipeline(document_id, settings)
    except Exception as e:
        logger.error("Erro ao gerar insights para documento %s: %s", document_id, e)
        _set_error_status(document_id)
        return InsightsResult(
            document_id=document_id,
            insights=[],
            success=False,
            error_message=f"Erro ao gerar insights: {e}",
        )


def _execute_insights_pipeline(document_id: str, settings) -> InsightsResult:
    """Core pipeline: fetch data, invoke Bedrock, validate, store results."""
    # Fetch document
    document = get_item(settings.dynamodb_documents_table, {"document_id": document_id})
    if not document:
        return InsightsResult(
            document_id=document_id, insights=[], success=False,
            error_message="Documento não encontrado.",
        )

    # Fetch extraction
    extraction = get_item(settings.dynamodb_extractions_table, {"document_id": document_id})
    if not extraction:
        return InsightsResult(
            document_id=document_id, insights=[], success=False,
            error_message="Extração não encontrada para o documento.",
        )

    # Invoke Bedrock
    fields_json = json.dumps(extraction.get("fields", []), ensure_ascii=False, indent=2)
    category = document.get("category", "Documento Genérico")
    user_prompt = format_insights_user_prompt(fields_json, category)

    response = invoke_claude_json(prompt=user_prompt, system=get_insights_system_prompt())

    if response is None:
        _set_error_status(document_id)
        return InsightsResult(
            document_id=document_id, insights=[], success=False,
            error_message="Timeout ao gerar insights. Tente novamente.",
        )

    # Parse and validate
    raw_insights = response.get("insights", [])
    insights = _parse_insights(raw_insights if isinstance(raw_insights, list) else [])

    if not insights:
        insights = [DEFAULT_INSIGHT]

    # Calculate max severity and store
    max_severity = calculate_max_severity(insights)
    now = datetime.now(UTC).isoformat()

    for insight in insights:
        put_item(settings.dynamodb_insights_table, {
            "insight_id": str(uuid.uuid4()),
            "document_id": document_id,
            "title": insight.title,
            "description": insight.description,
            "category": insight.category.value,
            "severity": insight.severity.value,
            "created_at": now,
        })

    update_item(
        settings.dynamodb_documents_table,
        {"document_id": document_id},
        {"status": "pending_review", "max_severity": max_severity, "processed_at": now},
    )

    return InsightsResult(document_id=document_id, insights=insights, success=True)
