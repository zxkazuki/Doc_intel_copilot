"""Unit tests for modules/history.py — document history and detail queries."""

import uuid
from datetime import UTC, date, datetime

import boto3
import pytest
from moto import mock_aws

from config import get_settings
from modules.history import (
    HistoryFilters,
    PaginatedResult,
    get_document_detail,
    get_document_history,
    _apply_filters,
    _matches_category,
    _matches_date_range,
    _matches_search_text,
    _matches_status,
    _paginate,
)


@pytest.fixture
def dynamodb_tables():
    """Create all mock DynamoDB tables for testing."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        settings = get_settings()

        # Documents table
        client.create_table(
            TableName=settings.dynamodb_documents_table,
            KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "document_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Extractions table
        client.create_table(
            TableName=settings.dynamodb_extractions_table,
            KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "document_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Insights table (with document-index GSI)
        client.create_table(
            TableName=settings.dynamodb_insights_table,
            KeySchema=[
                {"AttributeName": "insight_id", "KeyType": "HASH"},
                {"AttributeName": "document_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "insight_id", "AttributeType": "S"},
                {"AttributeName": "document_id", "AttributeType": "S"},
                {"AttributeName": "severity", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "document-index",
                    "KeySchema": [
                        {"AttributeName": "document_id", "KeyType": "HASH"},
                        {"AttributeName": "severity", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # HumanReviews table (with document-index GSI)
        client.create_table(
            TableName=settings.dynamodb_reviews_table,
            KeySchema=[
                {"AttributeName": "review_id", "KeyType": "HASH"},
                {"AttributeName": "document_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "review_id", "AttributeType": "S"},
                {"AttributeName": "document_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "document-index",
                    "KeySchema": [
                        {"AttributeName": "document_id", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield


def _seed_documents(count: int, **overrides) -> list[str]:
    """Insert documents into DynamoDB and return their IDs."""
    settings = get_settings()
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    table = resource.Table(settings.dynamodb_documents_table)
    ids = []

    for i in range(count):
        doc_id = str(uuid.uuid4())
        item = {
            "document_id": doc_id,
            "file_name": f"doc_{i}.pdf",
            "category": "Contrato",
            "status": "pending_review",
            "processed_at": f"2024-01-{15 - i:02d}T10:00:00+00:00",
            "file_format": "pdf",
            "file_size_bytes": 1024,
        }
        item.update(overrides)
        table.put_item(Item=item)
        ids.append(doc_id)

    return ids


class TestMatchersUnit:
    """Unit tests for individual filter matcher functions."""

    def test_matches_category_none_returns_true(self) -> None:
        assert _matches_category({"category": "Contrato"}, None) is True

    def test_matches_category_match(self) -> None:
        assert _matches_category({"category": "Contrato"}, "Contrato") is True

    def test_matches_category_no_match(self) -> None:
        assert _matches_category({"category": "Contrato"}, "Laudo Médico") is False

    def test_matches_status_none_returns_true(self) -> None:
        assert _matches_status({"status": "approved"}, None) is True

    def test_matches_status_match(self) -> None:
        assert _matches_status({"status": "approved"}, "approved") is True

    def test_matches_status_no_match(self) -> None:
        assert _matches_status({"status": "approved"}, "rejected") is False

    def test_matches_date_range_none_returns_true(self) -> None:
        assert _matches_date_range({"processed_at": "2024-01-10T10:00:00"}, None, None) is True

    def test_matches_date_range_in_range(self) -> None:
        doc = {"processed_at": "2024-01-10T10:00:00+00:00"}
        assert _matches_date_range(doc, date(2024, 1, 1), date(2024, 1, 31)) is True

    def test_matches_date_range_before(self) -> None:
        doc = {"processed_at": "2023-12-31T10:00:00+00:00"}
        assert _matches_date_range(doc, date(2024, 1, 1), None) is False

    def test_matches_date_range_after(self) -> None:
        doc = {"processed_at": "2024-02-01T10:00:00+00:00"}
        assert _matches_date_range(doc, None, date(2024, 1, 31)) is False

    def test_matches_date_range_no_processed_at(self) -> None:
        assert _matches_date_range({}, date(2024, 1, 1), None) is False

    def test_matches_search_text_none_returns_true(self) -> None:
        assert _matches_search_text({"file_name": "doc.pdf"}, None) is True

    def test_matches_search_text_short_returns_true(self) -> None:
        assert _matches_search_text({"file_name": "doc.pdf"}, "ab") is True

    def test_matches_search_text_found(self) -> None:
        assert _matches_search_text({"file_name": "contrato_empresa.pdf"}, "contrato") is True

    def test_matches_search_text_case_insensitive(self) -> None:
        assert _matches_search_text({"file_name": "CONTRATO.pdf"}, "contrato") is True

    def test_matches_search_text_not_found(self) -> None:
        assert _matches_search_text({"file_name": "laudo.pdf"}, "contrato") is False


class TestPaginate:
    """Unit tests for pagination logic."""

    def test_first_page(self) -> None:
        items = [{"id": i} for i in range(50)]
        result = _paginate(items, page=1, page_size=20)
        assert result.total == 50
        assert len(result.items) == 20
        assert result.page == 1
        assert result.has_next is True

    def test_last_page(self) -> None:
        items = [{"id": i} for i in range(50)]
        result = _paginate(items, page=3, page_size=20)
        assert len(result.items) == 10
        assert result.has_next is False

    def test_exact_page_boundary(self) -> None:
        items = [{"id": i} for i in range(40)]
        result = _paginate(items, page=2, page_size=20)
        assert len(result.items) == 20
        assert result.has_next is False

    def test_empty_items(self) -> None:
        result = _paginate([], page=1, page_size=20)
        assert result.total == 0
        assert result.items == []
        assert result.has_next is False

    def test_single_page(self) -> None:
        items = [{"id": i} for i in range(5)]
        result = _paginate(items, page=1, page_size=20)
        assert result.total == 5
        assert len(result.items) == 5
        assert result.has_next is False


class TestGetDocumentHistory:
    """Integration tests for get_document_history with mocked DynamoDB."""

    @mock_aws
    def test_returns_all_documents_no_filters(self, dynamodb_tables) -> None:
        _seed_documents(5)
        result = get_document_history(HistoryFilters())
        assert result.total == 5
        assert len(result.items) == 5

    @mock_aws
    def test_sorted_by_processed_at_descending(self, dynamodb_tables) -> None:
        _seed_documents(3)
        result = get_document_history(HistoryFilters())
        dates = [item["processed_at"] for item in result.items]
        assert dates == sorted(dates, reverse=True)

    @mock_aws
    def test_filter_by_category(self, dynamodb_tables) -> None:
        _seed_documents(3, category="Contrato")
        _seed_documents(2, category="Laudo Médico")
        result = get_document_history(HistoryFilters(category="Laudo Médico"))
        assert result.total == 2
        assert all(item["category"] == "Laudo Médico" for item in result.items)

    @mock_aws
    def test_filter_by_status(self, dynamodb_tables) -> None:
        _seed_documents(3, status="approved")
        _seed_documents(2, status="pending_review")
        result = get_document_history(HistoryFilters(status="approved"))
        assert result.total == 3

    @mock_aws
    def test_filter_by_date_range(self, dynamodb_tables) -> None:
        settings = get_settings()
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        table = resource.Table(settings.dynamodb_documents_table)

        table.put_item(Item={
            "document_id": str(uuid.uuid4()),
            "file_name": "jan.pdf",
            "processed_at": "2024-01-15T10:00:00+00:00",
            "category": "Contrato",
            "status": "approved",
        })
        table.put_item(Item={
            "document_id": str(uuid.uuid4()),
            "file_name": "feb.pdf",
            "processed_at": "2024-02-15T10:00:00+00:00",
            "category": "Contrato",
            "status": "approved",
        })

        result = get_document_history(HistoryFilters(
            date_from=date(2024, 2, 1), date_to=date(2024, 2, 28)
        ))
        assert result.total == 1
        assert result.items[0]["file_name"] == "feb.pdf"

    @mock_aws
    def test_filter_by_search_text(self, dynamodb_tables) -> None:
        settings = get_settings()
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        table = resource.Table(settings.dynamodb_documents_table)

        table.put_item(Item={
            "document_id": str(uuid.uuid4()),
            "file_name": "contrato_empresa.pdf",
            "processed_at": "2024-01-15T10:00:00+00:00",
            "category": "Contrato",
            "status": "approved",
        })
        table.put_item(Item={
            "document_id": str(uuid.uuid4()),
            "file_name": "laudo_medico.pdf",
            "processed_at": "2024-01-14T10:00:00+00:00",
            "category": "Laudo Médico",
            "status": "approved",
        })

        result = get_document_history(HistoryFilters(search_text="contrato"))
        assert result.total == 1
        assert "contrato" in result.items[0]["file_name"]

    @mock_aws
    def test_search_text_less_than_3_chars_ignored(self, dynamodb_tables) -> None:
        _seed_documents(3)
        result = get_document_history(HistoryFilters(search_text="ab"))
        assert result.total == 3

    @mock_aws
    def test_pagination(self, dynamodb_tables) -> None:
        _seed_documents(25)
        page1 = get_document_history(HistoryFilters(page=1, page_size=20))
        assert len(page1.items) == 20
        assert page1.has_next is True
        assert page1.total == 25

        page2 = get_document_history(HistoryFilters(page=2, page_size=20))
        assert len(page2.items) == 5
        assert page2.has_next is False

    @mock_aws
    def test_empty_result(self, dynamodb_tables) -> None:
        result = get_document_history(HistoryFilters(category="Nota Fiscal"))
        assert result.total == 0
        assert result.items == []
        assert result.has_next is False


class TestGetDocumentDetail:
    """Integration tests for get_document_detail with mocked DynamoDB."""

    @mock_aws
    def test_returns_all_data(self, dynamodb_tables) -> None:
        settings = get_settings()
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        doc_id = str(uuid.uuid4())

        resource.Table(settings.dynamodb_documents_table).put_item(Item={
            "document_id": doc_id,
            "file_name": "contrato.pdf",
            "category": "Contrato",
            "status": "pending_review",
        })

        resource.Table(settings.dynamodb_extractions_table).put_item(Item={
            "document_id": doc_id,
            "fields": [{"name": "Partes", "value": "A e B", "confidence": "0.9"}],
        })

        resource.Table(settings.dynamodb_insights_table).put_item(Item={
            "insight_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "title": "Insight 1",
            "severity": "High",
        })

        resource.Table(settings.dynamodb_reviews_table).put_item(Item={
            "review_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "action": "correction",
            "timestamp": datetime.now(UTC).isoformat(),
        })

        result = get_document_detail(doc_id)

        assert result is not None
        assert result["document"]["document_id"] == doc_id
        assert result["extraction"]["document_id"] == doc_id
        assert len(result["insights"]) == 1
        assert len(result["reviews"]) == 1

    @mock_aws
    def test_returns_none_for_nonexistent_document(self, dynamodb_tables) -> None:
        result = get_document_detail("nonexistent-id")
        assert result is None

    @mock_aws
    def test_returns_data_without_extraction(self, dynamodb_tables) -> None:
        settings = get_settings()
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        doc_id = str(uuid.uuid4())

        resource.Table(settings.dynamodb_documents_table).put_item(Item={
            "document_id": doc_id,
            "file_name": "doc.pdf",
            "status": "uploaded",
        })

        result = get_document_detail(doc_id)

        assert result is not None
        assert result["document"]["document_id"] == doc_id
        assert result["extraction"] is None
        assert result["insights"] == []
        assert result["reviews"] == []


# =============================================================================
# Property-Based Tests (Hypothesis)
# =============================================================================

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# --- Hypothesis Generators ---

VALID_CATEGORIES = [
    "Contrato", "Laudo Médico", "Extrato Bancário",
    "Ficha Cadastral", "Nota Fiscal", "Documento Genérico",
]

VALID_STATUSES = [
    "uploaded", "classifying", "classified", "extracting", "extracted",
    "generating_insights", "pending_review", "approved", "rejected",
]


@st.composite
def document_dicts(draw, count=None):
    """Generate a list of document dicts with random metadata."""
    n = count if count is not None else draw(st.integers(min_value=0, max_value=50))
    docs = []
    for i in range(n):
        year = draw(st.integers(min_value=2020, max_value=2025))
        month = draw(st.integers(min_value=1, max_value=12))
        day = draw(st.integers(min_value=1, max_value=28))
        hour = draw(st.integers(min_value=0, max_value=23))
        minute = draw(st.integers(min_value=0, max_value=59))
        doc = {
            "document_id": f"doc-{i}",
            "file_name": draw(st.from_regex(r"[a-z]{3,15}\.(pdf|png|jpg|jpeg)", fullmatch=True)),
            "category": draw(st.sampled_from(VALID_CATEGORIES)),
            "status": draw(st.sampled_from(VALID_STATUSES)),
            "processed_at": f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+00:00",
            "file_format": draw(st.sampled_from(["pdf", "png", "jpg", "jpeg"])),
            "file_size_bytes": draw(st.integers(min_value=100, max_value=20_000_000)),
        }
        docs.append(doc)
    return docs


@st.composite
def history_filters_strategy(draw):
    """Generate random HistoryFilters with optional fields."""
    category = draw(st.one_of(st.none(), st.sampled_from(VALID_CATEGORIES)))
    status = draw(st.one_of(st.none(), st.sampled_from(VALID_STATUSES)))

    date_from_val = draw(st.one_of(
        st.none(),
        st.dates(min_value=date(2020, 1, 1), max_value=date(2025, 12, 28)),
    ))
    date_to_val = draw(st.one_of(
        st.none(),
        st.dates(min_value=date(2020, 1, 1), max_value=date(2025, 12, 28)),
    ))
    if date_from_val and date_to_val and date_from_val > date_to_val:
        date_from_val, date_to_val = date_to_val, date_from_val

    search_text = draw(st.one_of(
        st.none(),
        st.text(min_size=1, max_size=2, alphabet="abcdefghij"),
        st.text(min_size=3, max_size=10, alphabet="abcdefghij"),
    ))

    return HistoryFilters(
        category=category,
        status=status,
        date_from=date_from_val,
        date_to=date_to_val,
        search_text=search_text,
        page=draw(st.integers(min_value=1, max_value=10)),
        page_size=draw(st.integers(min_value=1, max_value=50)),
    )


# --- Property 14: Pagination correctness ---
# Feature: document-intelligence-copilot, Property 14: Pagination correctness

class TestPaginationProperty:
    """
    Property 14: Pagination correctness

    For any set of documents and pagination parameters (page, page_size),
    the returned page SHALL contain at most page_size items,
    has_next SHALL be true iff there are more items beyond the current page,
    and total SHALL equal the full count of matching documents.

    **Validates: Requirements 7.2**
    """

    @given(
        items=document_dicts(),
        page=st.integers(min_value=1, max_value=20),
        page_size=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=20)
    def test_page_size_constraint(self, items: list[dict], page: int, page_size: int) -> None:
        """Returned page has at most page_size items."""
        result = _paginate(items, page, page_size)
        assert len(result.items) <= page_size

    @given(
        items=document_dicts(),
        page=st.integers(min_value=1, max_value=20),
        page_size=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=20)
    def test_has_next_correctness(self, items: list[dict], page: int, page_size: int) -> None:
        """has_next is True iff total > page * page_size."""
        result = _paginate(items, page, page_size)
        expected_has_next = len(items) > page * page_size
        assert result.has_next == expected_has_next

    @given(
        items=document_dicts(),
        page=st.integers(min_value=1, max_value=20),
        page_size=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=20)
    def test_total_equals_input_length(self, items: list[dict], page: int, page_size: int) -> None:
        """total SHALL equal the full count of items passed in."""
        result = _paginate(items, page, page_size)
        assert result.total == len(items)

    @given(
        items=document_dicts(),
        page=st.integers(min_value=1, max_value=20),
        page_size=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=20)
    def test_items_are_correct_slice(self, items: list[dict], page: int, page_size: int) -> None:
        """Returned items are the correct slice of input."""
        result = _paginate(items, page, page_size)
        start = (page - 1) * page_size
        end = start + page_size
        assert result.items == items[start:end]

    @given(
        items=document_dicts(),
        page=st.integers(min_value=1, max_value=20),
        page_size=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=20)
    def test_page_metadata_preserved(self, items: list[dict], page: int, page_size: int) -> None:
        """page and page_size metadata are preserved correctly."""
        result = _paginate(items, page, page_size)
        assert result.page == page
        assert result.page_size == page_size


# --- Property 15: Filter correctness ---
# Feature: document-intelligence-copilot, Property 15: Filter correctness

class TestFilterProperty:
    """
    Property 15: Filter correctness

    For any set of documents and applied filters, every returned document SHALL
    satisfy all active filter conditions. No document matching all conditions
    SHALL be excluded from the results.

    **Validates: Requirements 7.3, 7.4**
    """

    @given(documents=document_dicts(), filters=history_filters_strategy())
    @settings(max_examples=20)
    def test_all_returned_items_satisfy_filters(
        self, documents: list[dict], filters: HistoryFilters
    ) -> None:
        """Every item in result satisfies all active filter conditions."""
        result = _apply_filters(documents, filters)

        for doc in result:
            if filters.category is not None:
                assert doc["category"] == filters.category
            if filters.status is not None:
                assert doc["status"] == filters.status
            if filters.date_from is not None or filters.date_to is not None:
                doc_date = date.fromisoformat(doc["processed_at"][:10])
                if filters.date_from:
                    assert doc_date >= filters.date_from
                if filters.date_to:
                    assert doc_date <= filters.date_to
            if filters.search_text and len(filters.search_text) >= 3:
                assert filters.search_text.lower() in doc.get("file_name", "").lower()

    @given(documents=document_dicts(), filters=history_filters_strategy())
    @settings(max_examples=20)
    def test_no_matching_item_excluded(
        self, documents: list[dict], filters: HistoryFilters
    ) -> None:
        """No document matching all conditions is excluded from the results."""
        result = _apply_filters(documents, filters)
        result_ids = {doc["document_id"] for doc in result}

        for doc in documents:
            if not _doc_matches_all_filters(doc, filters):
                continue
            assert doc["document_id"] in result_ids, (
                f"Document {doc['document_id']} matches all filters but was excluded"
            )


def _doc_matches_all_filters(doc: dict, filters: HistoryFilters) -> bool:
    """Helper: independently check if a document matches all filter conditions."""
    if filters.category is not None and doc.get("category") != filters.category:
        return False
    if filters.status is not None and doc.get("status") != filters.status:
        return False

    if filters.date_from is not None or filters.date_to is not None:
        processed_at = doc.get("processed_at")
        if not processed_at:
            return False
        try:
            doc_date = date.fromisoformat(processed_at[:10])
        except (ValueError, TypeError):
            return False
        if filters.date_from and doc_date < filters.date_from:
            return False
        if filters.date_to and doc_date > filters.date_to:
            return False

    if filters.search_text and len(filters.search_text) >= 3:
        if filters.search_text.lower() not in doc.get("file_name", "").lower():
            return False

    return True
