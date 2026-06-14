"""Unit tests for modules/insights.py — insight generation and validation."""

import uuid
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from modules.insights import (
    InsightSeverity,
    InsightCategory,
    Insight,
    calculate_max_severity,
    generate_insights,
    _parse_insights,
    _try_parse_insight,
    DEFAULT_INSIGHT,
)
from config import get_settings


@pytest.fixture
def dynamodb_tables():
    """Create mock DynamoDB tables for testing."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        settings = get_settings()

        for table_name, key_schema, attrs in [
            (settings.dynamodb_documents_table,
             [{"AttributeName": "document_id", "KeyType": "HASH"}],
             [{"AttributeName": "document_id", "AttributeType": "S"}]),
            (settings.dynamodb_extractions_table,
             [{"AttributeName": "document_id", "KeyType": "HASH"}],
             [{"AttributeName": "document_id", "AttributeType": "S"}]),
            (settings.dynamodb_insights_table,
             [{"AttributeName": "insight_id", "KeyType": "HASH"},
              {"AttributeName": "document_id", "KeyType": "RANGE"}],
             [{"AttributeName": "insight_id", "AttributeType": "S"},
              {"AttributeName": "document_id", "AttributeType": "S"}]),
        ]:
            client.create_table(
                TableName=table_name,
                KeySchema=key_schema,
                AttributeDefinitions=attrs,
                BillingMode="PAY_PER_REQUEST",
            )

        yield


@pytest.fixture
def doc_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def seeded_doc(dynamodb_tables, doc_id):
    """Seed a document and its extraction in DynamoDB."""
    settings = get_settings()
    resource = boto3.resource("dynamodb", region_name="us-east-1")

    resource.Table(settings.dynamodb_documents_table).put_item(Item={
        "document_id": doc_id,
        "file_name": "contrato.pdf",
        "category": "Contrato",
        "status": "extracted",
    })

    resource.Table(settings.dynamodb_extractions_table).put_item(Item={
        "document_id": doc_id,
        "fields": [
            {"name": "Partes", "value": "Empresa A e Empresa B", "confidence": "0.95"},
            {"name": "Valor", "value": "R$ 50.000,00", "confidence": "0.90"},
            {"name": "Prazo", "value": "12 meses", "confidence": "0.88"},
            {"name": "Assinaturas", "value": None, "confidence": "0.0"},
        ],
    })

    return doc_id


class TestTryParseInsight:
    def test_valid_insight(self) -> None:
        raw = {"title": "Assinatura ausente", "description": "Não localizado.",
               "category": "Compliance", "severity": "High"}
        result = _try_parse_insight(raw)
        assert result is not None
        assert result.category == InsightCategory.COMPLIANCE
        assert result.severity == InsightSeverity.HIGH

    def test_invalid_category_returns_none(self) -> None:
        assert _try_parse_insight(
            {"title": "T", "description": "D", "category": "Invalid", "severity": "Low"}
        ) is None

    def test_invalid_severity_returns_none(self) -> None:
        assert _try_parse_insight(
            {"title": "T", "description": "D", "category": "Compliance", "severity": "Unknown"}
        ) is None

    def test_truncates_title_to_100(self) -> None:
        result = _try_parse_insight(
            {"title": "A" * 200, "description": "D", "category": "Qualidade", "severity": "Medium"}
        )
        assert len(result.title) == 100

    def test_truncates_description_to_500(self) -> None:
        result = _try_parse_insight(
            {"title": "T", "description": "B" * 1000, "category": "Financeiro", "severity": "Critical"}
        )
        assert len(result.description) == 500

    def test_empty_dict_returns_none(self) -> None:
        assert _try_parse_insight({}) is None


class TestParseInsights:
    def test_clamps_to_max_20(self) -> None:
        raw_list = [
            {"title": f"I{i}", "description": "D", "category": "Operacional", "severity": "Low"}
            for i in range(30)
        ]
        assert len(_parse_insights(raw_list)) == 20

    def test_filters_invalid_entries(self) -> None:
        raw_list = [
            {"title": "Valid", "description": "D", "category": "Compliance", "severity": "High"},
            {"title": "Bad", "description": "D", "category": "BadCat", "severity": "High"},
        ]
        result = _parse_insights(raw_list)
        assert len(result) == 1
        assert result[0].title == "Valid"

    def test_empty_list(self) -> None:
        assert _parse_insights([]) == []


class TestCalculateMaxSeverity:
    def test_single_low(self) -> None:
        insights = [Insight("T", "D", InsightCategory.OPERACIONAL, InsightSeverity.LOW)]
        assert calculate_max_severity(insights) == "Low"

    def test_mixed_returns_highest(self) -> None:
        insights = [
            Insight("T1", "D1", InsightCategory.OPERACIONAL, InsightSeverity.LOW),
            Insight("T2", "D2", InsightCategory.COMPLIANCE, InsightSeverity.CRITICAL),
            Insight("T3", "D3", InsightCategory.FINANCEIRO, InsightSeverity.HIGH),
        ]
        assert calculate_max_severity(insights) == "Critical"

    def test_empty_list_returns_low(self) -> None:
        assert calculate_max_severity([]) == "Low"


class TestGenerateInsights:
    @mock_aws
    def test_successful_generation(self, seeded_doc) -> None:
        bedrock_response = {"insights": [
            {"title": "Assinatura não identificada", "description": "Não localizado.",
             "category": "Compliance", "severity": "High"},
            {"title": "Documento completo", "description": "OK.",
             "category": "Operacional", "severity": "Low"},
        ]}

        with patch("modules.insights.invoke_claude_json", return_value=bedrock_response):
            result = generate_insights(seeded_doc)

        assert result.success is True
        assert len(result.insights) == 2
        assert result.insights[0].severity == InsightSeverity.HIGH

    @mock_aws
    def test_document_not_found(self, dynamodb_tables) -> None:
        result = generate_insights("nonexistent-id")
        assert result.success is False
        assert "não encontrado" in result.error_message

    @mock_aws
    def test_extraction_not_found(self, dynamodb_tables) -> None:
        settings = get_settings()
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        doc_id = str(uuid.uuid4())
        resource.Table(settings.dynamodb_documents_table).put_item(
            Item={"document_id": doc_id, "category": "Contrato", "status": "extracted"}
        )

        result = generate_insights(doc_id)
        assert result.success is False
        assert "Extração não encontrada" in result.error_message

    @mock_aws
    def test_bedrock_timeout_sets_error_status(self, seeded_doc) -> None:
        with patch("modules.insights.invoke_claude_json", return_value=None):
            result = generate_insights(seeded_doc)

        assert result.success is False
        assert "Timeout" in result.error_message

        settings = get_settings()
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        doc = resource.Table(settings.dynamodb_documents_table).get_item(
            Key={"document_id": seeded_doc}
        )["Item"]
        assert doc["status"] == "insights_error"

    @mock_aws
    def test_empty_response_generates_default_insight(self, seeded_doc) -> None:
        with patch("modules.insights.invoke_claude_json", return_value={"insights": []}):
            result = generate_insights(seeded_doc)

        assert result.success is True
        assert len(result.insights) == 1
        assert result.insights[0].category == InsightCategory.OPERACIONAL
        assert result.insights[0].severity == InsightSeverity.LOW

    @mock_aws
    def test_updates_document_with_pending_review_and_max_severity(self, seeded_doc) -> None:
        bedrock_response = {"insights": [
            {"title": "Critical", "description": "D", "category": "Compliance", "severity": "Critical"},
        ]}

        with patch("modules.insights.invoke_claude_json", return_value=bedrock_response):
            generate_insights(seeded_doc)

        settings = get_settings()
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        doc = resource.Table(settings.dynamodb_documents_table).get_item(
            Key={"document_id": seeded_doc}
        )["Item"]

        assert doc["status"] == "pending_review"
        assert doc["max_severity"] == "Critical"
        assert "processed_at" in doc

    @mock_aws
    def test_stores_insights_in_insights_table(self, seeded_doc) -> None:
        bedrock_response = {"insights": [
            {"title": "I1", "description": "D1", "category": "Qualidade", "severity": "Medium"},
            {"title": "I2", "description": "D2", "category": "Financeiro", "severity": "High"},
        ]}

        with patch("modules.insights.invoke_claude_json", return_value=bedrock_response):
            generate_insights(seeded_doc)

        settings = get_settings()
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        items = resource.Table(settings.dynamodb_insights_table).scan()["Items"]
        assert len(items) == 2
        assert all(item["document_id"] == seeded_doc for item in items)

    @mock_aws
    def test_exception_sets_error_status(self, seeded_doc) -> None:
        with patch("modules.insights.invoke_claude_json", side_effect=ValueError("parse error")):
            result = generate_insights(seeded_doc)

        assert result.success is False

        settings = get_settings()
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        doc = resource.Table(settings.dynamodb_documents_table).get_item(
            Key={"document_id": seeded_doc}
        )["Item"]
        assert doc["status"] == "insights_error"


# Feature: document-intelligence-copilot, Property 8: Insights count is within bounds
# Feature: document-intelligence-copilot, Property 9: Insight structure respects constraints
# Feature: document-intelligence-copilot, Property 10: Severity assignment follows defined mapping

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from prompts.insights import SEVERITY_MAPPING

# --- Strategies ---

random_titles = st.text(min_size=0, max_size=200)
random_descriptions = st.text(min_size=0, max_size=1000)

valid_raw_insight = st.fixed_dictionaries({
    "title": random_titles,
    "description": random_descriptions,
    "category": st.sampled_from([c.value for c in InsightCategory]),
    "severity": st.sampled_from([s.value for s in InsightSeverity]),
})

raw_insight_lists = st.lists(valid_raw_insight, min_size=1, max_size=30)

invalid_raw_insight = st.fixed_dictionaries({
    "title": random_titles,
    "description": random_descriptions,
    "category": st.text(min_size=1, max_size=30),
    "severity": st.text(min_size=1, max_size=30),
})

mixed_raw_insight_lists = st.lists(
    st.one_of(valid_raw_insight, invalid_raw_insight),
    min_size=0,
    max_size=30,
)


class TestProperty8InsightsCountBounds:
    """
    Property 8: Insights count is within bounds.

    For any successful insights generation result, the number of insights
    SHALL be between 1 and 20 inclusive.

    **Validates: Requirements 4.1**
    """

    @given(raw_list=raw_insight_lists)
    @h_settings(max_examples=100)
    def test_parse_insights_returns_at_most_20(self, raw_list: list[dict]) -> None:
        """_parse_insights never returns more than 20 insights."""
        result = _parse_insights(raw_list)
        assert len(result) <= 20

    @given(raw_list=mixed_raw_insight_lists)
    @h_settings(max_examples=100)
    def test_parse_insights_count_bounded_with_mixed_input(self, raw_list: list[dict]) -> None:
        """_parse_insights always returns 0–20 items regardless of input validity."""
        result = _parse_insights(raw_list)
        assert 0 <= len(result) <= 20

    @given(raw_list=mixed_raw_insight_lists)
    @h_settings(max_examples=100)
    def test_full_pipeline_ensures_at_least_one_insight(self, raw_list: list[dict]) -> None:
        """After DEFAULT_INSIGHT fallback (pipeline behavior), result has 1–20 insights."""
        parsed = _parse_insights(raw_list)
        if not parsed:
            parsed = [DEFAULT_INSIGHT]
        assert 1 <= len(parsed) <= 20


class TestProperty9InsightStructureConstraints:
    """
    Property 9: Insight structure respects constraints.

    For any generated insight, title ≤ 100 chars, description ≤ 500 chars,
    category ∈ InsightCategory, severity ∈ InsightSeverity.

    **Validates: Requirements 4.3, 4.5**
    """

    @given(raw_list=raw_insight_lists)
    @h_settings(max_examples=100)
    def test_parsed_insights_title_bounded(self, raw_list: list[dict]) -> None:
        """After parsing, every insight title is ≤ 100 characters."""
        for insight in _parse_insights(raw_list):
            assert len(insight.title) <= 100

    @given(raw_list=raw_insight_lists)
    @h_settings(max_examples=100)
    def test_parsed_insights_description_bounded(self, raw_list: list[dict]) -> None:
        """After parsing, every insight description is ≤ 500 characters."""
        for insight in _parse_insights(raw_list):
            assert len(insight.description) <= 500

    @given(raw_list=raw_insight_lists)
    @h_settings(max_examples=100)
    def test_parsed_insights_category_valid(self, raw_list: list[dict]) -> None:
        """After parsing, every insight has a valid InsightCategory."""
        for insight in _parse_insights(raw_list):
            assert insight.category in set(InsightCategory)

    @given(raw_list=raw_insight_lists)
    @h_settings(max_examples=100)
    def test_parsed_insights_severity_valid(self, raw_list: list[dict]) -> None:
        """After parsing, every insight has a valid InsightSeverity."""
        for insight in _parse_insights(raw_list):
            assert insight.severity in set(InsightSeverity)

    @given(
        title=st.text(min_size=0, max_size=200),
        description=st.text(min_size=0, max_size=1000),
        category=st.sampled_from([c.value for c in InsightCategory]),
        severity=st.sampled_from([s.value for s in InsightSeverity]),
    )
    @h_settings(max_examples=100)
    def test_single_insight_all_constraints(
        self, title: str, description: str, category: str, severity: str
    ) -> None:
        """_try_parse_insight enforces all structural constraints on a single insight."""
        raw = {"title": title, "description": description, "category": category, "severity": severity}
        result = _try_parse_insight(raw)
        assert result is not None
        assert len(result.title) <= 100
        assert len(result.description) <= 500
        assert result.category in set(InsightCategory)
        assert result.severity in set(InsightSeverity)


class TestProperty10SeverityMapping:
    """
    Property 10: Severity assignment follows defined mapping.

    For any detected condition in the mapping table, the assigned severity
    SHALL match the predefined SEVERITY_MAPPING.

    **Validates: Requirements 4.4**
    """

    @given(condition=st.sampled_from(list(SEVERITY_MAPPING.keys())))
    @h_settings(max_examples=100)
    def test_mapping_produces_valid_severity_and_category(self, condition: str) -> None:
        """Every condition maps to a valid severity and category."""
        severity, category = SEVERITY_MAPPING[condition]
        assert severity in {s.value for s in InsightSeverity}
        assert category in {c.value for c in InsightCategory}

    def test_all_mapping_entries_valid(self) -> None:
        """Exhaustive: every SEVERITY_MAPPING entry has valid severity and category."""
        valid_severities = {s.value for s in InsightSeverity}
        valid_categories = {c.value for c in InsightCategory}
        for condition, (severity, category) in SEVERITY_MAPPING.items():
            assert severity in valid_severities, f"'{condition}' → invalid severity '{severity}'"
            assert category in valid_categories, f"'{condition}' → invalid category '{category}'"

    def test_mapping_covers_all_spec_conditions(self) -> None:
        """The mapping covers all 7 condition types from the specification."""
        expected = {
            "Campos obrigatórios ausentes",
            "Informações conflitantes",
            "Valores divergentes",
            "Assinatura não identificada",
            "Campos opcionais ausentes",
            "Datas inválidas",
            "Observações informativas",
        }
        assert set(SEVERITY_MAPPING.keys()) == expected

    def test_specific_severity_values_match_spec(self) -> None:
        """Exact values match the design document severity mapping table."""
        assert SEVERITY_MAPPING["Campos obrigatórios ausentes"] == ("Critical", "Qualidade")
        assert SEVERITY_MAPPING["Informações conflitantes"] == ("Critical", "Compliance")
        assert SEVERITY_MAPPING["Valores divergentes"] == ("High", "Financeiro")
        assert SEVERITY_MAPPING["Assinatura não identificada"] == ("High", "Compliance")
        assert SEVERITY_MAPPING["Campos opcionais ausentes"] == ("Medium", "Qualidade")
        assert SEVERITY_MAPPING["Datas inválidas"] == ("Medium", "Operacional")
        assert SEVERITY_MAPPING["Observações informativas"] == ("Low", "Operacional")

    @given(condition=st.sampled_from(list(SEVERITY_MAPPING.keys())))
    @h_settings(max_examples=100)
    def test_severity_order_consistent_with_mapping(self, condition: str) -> None:
        """SEVERITY_ORDER dict recognizes all severities from the mapping."""
        from modules.insights import SEVERITY_ORDER
        severity, _ = SEVERITY_MAPPING[condition]
        assert severity in SEVERITY_ORDER
