"""Dashboard module — aggregates KPIs, insights, alerts, and recent documents."""

import logging
from dataclasses import dataclass, field

from config import get_settings
from infrastructure.dynamodb_client import scan_items

logger = logging.getLogger(__name__)

SEVERITY_ORDER: dict[str, int] = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}

VALID_CATEGORIES = ["Compliance", "Qualidade", "Financeiro", "Operacional"]

PROCESSED_STATUSES = {"extracted", "pending_review", "approved", "rejected"}

PENDING_STATUSES = {
    "uploaded",
    "classifying",
    "classified",
    "extracting",
    "extracted",
    "generating_insights",
}


@dataclass
class DashboardKPIs:
    total_processed: int
    pending_documents: int
    pending_reviews: int
    critical_alerts: int


@dataclass
class DashboardData:
    kpis: DashboardKPIs
    insights_by_category: dict[str, list[dict]] = field(default_factory=dict)
    alerts: list[dict] = field(default_factory=list)
    recent_documents: list[dict] = field(default_factory=list)


def _scan_all_items(table_name: str, filter_expr: dict | None = None) -> list[dict]:
    """Scan entire table handling pagination."""
    all_items: list[dict] = []
    last_key = None

    while True:
        result = scan_items(
            table_name=table_name,
            filter_expr=filter_expr,
            exclusive_start_key=last_key,
        )
        all_items.extend(result["items"])
        last_key = result.get("last_evaluated_key")
        if not last_key:
            break

    return all_items


def _severity_score(item: dict) -> int:
    """Get numeric severity score for sorting."""
    return SEVERITY_ORDER.get(item.get("severity", "Low"), 0)


def _compute_kpis(documents: list[dict], critical_count: int) -> DashboardKPIs:
    """Compute KPI values from document list and critical alert count."""
    return DashboardKPIs(
        total_processed=sum(1 for d in documents if d.get("status") in PROCESSED_STATUSES),
        pending_documents=sum(1 for d in documents if d.get("status") in PENDING_STATUSES),
        pending_reviews=sum(1 for d in documents if d.get("status") == "pending_review"),
        critical_alerts=critical_count,
    )


def _group_insights_by_category(insights: list[dict]) -> dict[str, list[dict]]:
    """Group insights by category, max 5 per category, sorted by severity descending."""
    grouped: dict[str, list[dict]] = {cat: [] for cat in VALID_CATEGORIES}

    for insight in insights:
        category = insight.get("category", "")
        if category in grouped:
            grouped[category].append(insight)

    return {
        cat: sorted(items, key=_severity_score, reverse=True)[:5]
        for cat, items in grouped.items()
    }


def _build_alerts(insights: list[dict]) -> list[dict]:
    """Build alerts list: High/Critical insights, max 20, sorted Critical first."""
    high_critical = [i for i in insights if i.get("severity") in ("Critical", "High")]
    return sorted(high_critical, key=_severity_score, reverse=True)[:20]


def _get_recent_documents(documents: list[dict]) -> list[dict]:
    """Get 10 most recent documents sorted by processed_at descending."""
    with_date = [d for d in documents if d.get("processed_at")]
    return sorted(with_date, key=lambda d: d.get("processed_at", ""), reverse=True)[:10]


def _empty_dashboard() -> DashboardData:
    """Return an empty dashboard for error/empty states."""
    return DashboardData(
        kpis=DashboardKPIs(
            total_processed=0, pending_documents=0, pending_reviews=0, critical_alerts=0
        ),
        insights_by_category={cat: [] for cat in VALID_CATEGORIES},
        alerts=[],
        recent_documents=[],
    )


def get_dashboard_data() -> DashboardData:
    """Aggregate data from DynamoDB for the dashboard."""
    settings = get_settings()

    try:
        documents = _scan_all_items(settings.dynamodb_documents_table)
        all_insights = _scan_all_items(settings.dynamodb_insights_table)
    except Exception as e:
        logger.error("Erro ao carregar dados do dashboard: %s", e)
        return _empty_dashboard()

    critical_count = sum(1 for i in all_insights if i.get("severity") == "Critical")

    return DashboardData(
        kpis=_compute_kpis(documents, critical_count),
        insights_by_category=_group_insights_by_category(all_insights),
        alerts=_build_alerts(all_insights),
        recent_documents=_get_recent_documents(documents),
    )
