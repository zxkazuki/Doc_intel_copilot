"""History module — document history queries with filtering and pagination."""

import logging
from dataclasses import dataclass, field
from datetime import date

from config import get_settings
from infrastructure.dynamodb_client import get_item, query_items, scan_items

logger = logging.getLogger(__name__)


@dataclass
class HistoryFilters:
    category: str | None = None
    status: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    search_text: str | None = None  # min 3 chars
    page: int = 1
    page_size: int = 20


@dataclass
class PaginatedResult:
    items: list[dict] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    has_next: bool = False


def _matches_category(document: dict, category: str | None) -> bool:
    """Check if document matches the category filter."""
    if category is None:
        return True
    return document.get("category", "") == category


def _matches_status(document: dict, status: str | None) -> bool:
    """Check if document matches the status filter."""
    if status is None:
        return True
    return document.get("status", "") == status


def _matches_date_range(
    document: dict, date_from: date | None, date_to: date | None
) -> bool:
    """Check if document's processed_at falls within the date range."""
    if date_from is None and date_to is None:
        return True

    processed_at = document.get("processed_at")
    if not processed_at:
        return False

    try:
        doc_date = date.fromisoformat(processed_at[:10])
    except (ValueError, TypeError):
        return False

    if date_from and doc_date < date_from:
        return False
    if date_to and doc_date > date_to:
        return False

    return True


def _matches_search_text(document: dict, search_text: str | None) -> bool:
    """Check if document matches search text (case-insensitive in file_name)."""
    if search_text is None or len(search_text) < 3:
        return True
    return search_text.lower() in document.get("file_name", "").lower()


def _apply_filters(documents: list[dict], filters: HistoryFilters) -> list[dict]:
    """Apply all filters to a list of documents."""
    return [
        doc
        for doc in documents
        if _matches_category(doc, filters.category)
        and _matches_status(doc, filters.status)
        and _matches_date_range(doc, filters.date_from, filters.date_to)
        and _matches_search_text(doc, filters.search_text)
    ]


def _paginate(items: list[dict], page: int, page_size: int) -> PaginatedResult:
    """Apply pagination to a sorted list."""
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return PaginatedResult(
        items=items[start:end],
        total=total,
        page=page,
        page_size=page_size,
        has_next=page * page_size < total,
    )


def get_document_history(filters: HistoryFilters) -> PaginatedResult:
    """Return paginated and filtered document history.

    Scans Documents table, applies in-memory filters, sorts by
    processed_at descending, and paginates.
    """
    settings = get_settings()

    try:
        all_items: list[dict] = []
        last_key = None

        while True:
            result = scan_items(
                settings.dynamodb_documents_table,
                exclusive_start_key=last_key,
            )
            all_items.extend(result.get("items", []))
            last_key = result.get("last_evaluated_key")
            if not last_key:
                break

        filtered = _apply_filters(all_items, filters)
        sorted_items = sorted(
            filtered, key=lambda d: d.get("processed_at", ""), reverse=True
        )
        return _paginate(sorted_items, filters.page, filters.page_size)

    except Exception as e:
        logger.error("Erro ao buscar histórico de documentos: %s", e)
        return PaginatedResult()


def get_document_detail(document_id: str) -> dict | None:
    """Fetch all data for a document: metadata, extraction, insights, and reviews.

    Returns None if the document is not found.
    """
    settings = get_settings()

    try:
        document = get_item(
            settings.dynamodb_documents_table, {"document_id": document_id}
        )
        if not document:
            return None

        extraction = get_item(
            settings.dynamodb_extractions_table, {"document_id": document_id}
        )

        insights = query_items(
            settings.dynamodb_insights_table,
            key_condition={"document_id": document_id},
            index_name="document-index",
        )

        reviews = query_items(
            settings.dynamodb_reviews_table,
            key_condition={"document_id": document_id},
            index_name="document-index",
        )

        return {
            "document": document,
            "extraction": extraction,
            "insights": insights,
            "reviews": reviews,
        }

    except Exception as e:
        logger.error("Erro ao buscar detalhes do documento %s: %s", document_id, e)
        return None
