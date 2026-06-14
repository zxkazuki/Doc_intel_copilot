"""Integration tests for DynamoDB storage — CRUD on all 4 tables and GSI queries.

Validates: Requirements 1.2, 2.3, 3.8, 4.6, 5.6
"""

import uuid
from datetime import datetime, timezone

import boto3
import pytest
from moto import mock_aws

from infrastructure.dynamodb_client import (
    get_item,
    put_item,
    query_items,
    scan_items,
    update_item,
)


# ---------------------------------------------------------------------------
# Table creation helpers
# ---------------------------------------------------------------------------


def _create_documents_table(resource):
    """Create Documents table with status-index and category-index GSIs."""
    resource.create_table(
        TableName="Documents",
        KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "document_id", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
            {"AttributeName": "uploaded_at", "AttributeType": "S"},
            {"AttributeName": "category", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "status-index",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "uploaded_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "category-index",
                "KeySchema": [
                    {"AttributeName": "category", "KeyType": "HASH"},
                    {"AttributeName": "uploaded_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def _create_extractions_table(resource):
    """Create Extractions table with document_id as PK."""
    resource.create_table(
        TableName="Extractions",
        KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "document_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def _create_insights_table(resource):
    """Create Insights table with document-index GSI."""
    resource.create_table(
        TableName="Insights",
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


def _create_reviews_table(resource):
    """Create HumanReviews table with document-index GSI."""
    resource.create_table(
        TableName="HumanReviews",
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


def _create_all_tables(resource):
    """Create all 4 DynamoDB tables."""
    _create_documents_table(resource)
    _create_extractions_table(resource)
    _create_insights_table(resource)
    _create_reviews_table(resource)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dynamo_tables():
    """Provision all DynamoDB tables under moto mock."""
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        _create_all_tables(resource)
        yield resource


# ---------------------------------------------------------------------------
# Tests — Documents table CRUD
# ---------------------------------------------------------------------------


class TestDocumentsCrud:
    """Test CRUD operations on the Documents table."""

    def test_put_and_get_document(self, dynamo_tables):
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        item = {
            "document_id": doc_id,
            "file_name": "contract.pdf",
            "file_format": "pdf",
            "file_size_bytes": 1024000,
            "s3_key": f"documents/{doc_id}.pdf",
            "uploaded_at": now,
            "status": "uploaded",
        }

        put_item("Documents", item)
        result = get_item("Documents", {"document_id": doc_id})

        assert result is not None
        assert result["document_id"] == doc_id
        assert result["file_name"] == "contract.pdf"
        assert result["status"] == "uploaded"

    def test_update_document(self, dynamo_tables):
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        put_item("Documents", {
            "document_id": doc_id,
            "file_name": "invoice.pdf",
            "status": "uploaded",
            "uploaded_at": now,
        })

        update_item("Documents", {"document_id": doc_id}, {
            "status": "classified",
            "category": "Nota Fiscal",
            "classification_confidence": "0.95",
        })

        result = get_item("Documents", {"document_id": doc_id})
        assert result["status"] == "classified"
        assert result["category"] == "Nota Fiscal"

    def test_scan_documents(self, dynamo_tables):
        now = datetime.now(timezone.utc).isoformat()

        for i in range(3):
            put_item("Documents", {
                "document_id": str(uuid.uuid4()),
                "file_name": f"doc_{i}.pdf",
                "status": "uploaded",
                "uploaded_at": now,
            })

        result = scan_items("Documents")
        assert len(result["items"]) == 3
        assert result["last_evaluated_key"] is None


# ---------------------------------------------------------------------------
# Tests — Extractions table CRUD
# ---------------------------------------------------------------------------


class TestExtractionsCrud:
    """Test CRUD operations on the Extractions table."""

    def test_put_and_get_extraction(self, dynamo_tables):
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        item = {
            "document_id": doc_id,
            "fields": [
                {"name": "Partes", "value": "Empresa A e Empresa B", "confidence": "0.92"},
                {"name": "Valor", "value": "R$ 50.000,00", "confidence": "0.88"},
                {"name": "Prazo", "value": "12 meses", "confidence": "0.85"},
                {"name": "Assinaturas", "value": None, "confidence": "0.0"},
            ],
            "extracted_at": now,
        }

        put_item("Extractions", item)
        result = get_item("Extractions", {"document_id": doc_id})

        assert result is not None
        assert result["document_id"] == doc_id
        assert len(result["fields"]) == 4
        assert result["fields"][0]["name"] == "Partes"
        assert result["fields"][3]["value"] is None


# ---------------------------------------------------------------------------
# Tests — Insights table CRUD and GSI
# ---------------------------------------------------------------------------


class TestInsightsCrudAndGsi:
    """Test CRUD and document-index GSI on the Insights table."""

    def test_put_and_query_insights_by_document(self, dynamo_tables):
        doc_id = str(uuid.uuid4())

        insights = [
            {
                "insight_id": str(uuid.uuid4()),
                "document_id": doc_id,
                "title": "Campo obrigatório ausente",
                "description": "O campo Assinaturas não foi identificado no documento.",
                "category": "Qualidade",
                "severity": "Critical",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "insight_id": str(uuid.uuid4()),
                "document_id": doc_id,
                "title": "Valor divergente detectado",
                "description": "O valor total não corresponde à soma dos itens.",
                "category": "Financeiro",
                "severity": "High",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "insight_id": str(uuid.uuid4()),
                "document_id": doc_id,
                "title": "Observação informativa",
                "description": "Documento apresenta formatação padrão.",
                "category": "Operacional",
                "severity": "Low",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]

        for insight in insights:
            put_item("Insights", insight)

        # Query via document-index GSI
        results = query_items(
            "Insights",
            key_condition={"document_id": doc_id},
            index_name="document-index",
        )

        assert len(results) == 3
        assert all(r["document_id"] == doc_id for r in results)


# ---------------------------------------------------------------------------
# Tests — HumanReviews table CRUD and GSI
# ---------------------------------------------------------------------------


class TestReviewsCrudAndGsi:
    """Test CRUD and document-index GSI on the HumanReviews table."""

    def test_put_and_query_reviews_by_document(self, dynamo_tables):
        doc_id = str(uuid.uuid4())

        reviews = [
            {
                "review_id": str(uuid.uuid4()),
                "document_id": doc_id,
                "reviewer_id": "reviewer_001",
                "action": "correction",
                "field_name": "Valor",
                "original_value": "R$ 50.000",
                "new_value": "R$ 55.000",
                "timestamp": "2024-01-15T10:00:00Z",
            },
            {
                "review_id": str(uuid.uuid4()),
                "document_id": doc_id,
                "reviewer_id": "reviewer_001",
                "action": "approve",
                "field_name": None,
                "original_value": None,
                "new_value": None,
                "timestamp": "2024-01-15T10:05:00Z",
            },
        ]

        for review in reviews:
            put_item("HumanReviews", review)

        # Query via document-index GSI
        results = query_items(
            "HumanReviews",
            key_condition={"document_id": doc_id},
            index_name="document-index",
        )

        assert len(results) == 2
        assert all(r["document_id"] == doc_id for r in results)


# ---------------------------------------------------------------------------
# Tests — Status GSI query
# ---------------------------------------------------------------------------


class TestStatusGsiQuery:
    """Test status-index GSI on the Documents table."""

    def test_query_documents_by_status(self, dynamo_tables):
        docs = [
            {
                "document_id": str(uuid.uuid4()),
                "file_name": "pending1.pdf",
                "status": "pending_review",
                "uploaded_at": "2024-01-10T08:00:00Z",
            },
            {
                "document_id": str(uuid.uuid4()),
                "file_name": "pending2.pdf",
                "status": "pending_review",
                "uploaded_at": "2024-01-11T09:00:00Z",
            },
            {
                "document_id": str(uuid.uuid4()),
                "file_name": "approved1.pdf",
                "status": "approved",
                "uploaded_at": "2024-01-12T10:00:00Z",
            },
            {
                "document_id": str(uuid.uuid4()),
                "file_name": "uploaded1.pdf",
                "status": "uploaded",
                "uploaded_at": "2024-01-13T11:00:00Z",
            },
        ]

        for doc in docs:
            put_item("Documents", doc)

        # Query pending_review documents via status-index
        pending = query_items(
            "Documents",
            key_condition={"status": "pending_review"},
            index_name="status-index",
        )

        assert len(pending) == 2
        assert all(d["status"] == "pending_review" for d in pending)

        # Query approved documents
        approved = query_items(
            "Documents",
            key_condition={"status": "approved"},
            index_name="status-index",
        )

        assert len(approved) == 1
        assert approved[0]["file_name"] == "approved1.pdf"


# ---------------------------------------------------------------------------
# Tests — Cross-table consistency (full document lifecycle)
# ---------------------------------------------------------------------------


class TestCrossTableConsistency:
    """Verify data consistency across all tables for a processed document."""

    def test_full_document_lifecycle_consistency(self, dynamo_tables):
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # 1. Upload stage
        put_item("Documents", {
            "document_id": doc_id,
            "file_name": "contrato_servico.pdf",
            "file_format": "pdf",
            "file_size_bytes": 2048000,
            "s3_key": f"documents/{doc_id}.pdf",
            "uploaded_at": now,
            "status": "uploaded",
        })

        # 2. Classification stage
        update_item("Documents", {"document_id": doc_id}, {
            "status": "classified",
            "category": "Contrato",
            "classification_confidence": "0.92",
        })

        # 3. Extraction stage
        put_item("Extractions", {
            "document_id": doc_id,
            "fields": [
                {"name": "Partes", "value": "Empresa X e Empresa Y", "confidence": "0.95"},
                {"name": "Valor", "value": "R$ 120.000,00", "confidence": "0.90"},
                {"name": "Prazo", "value": "24 meses", "confidence": "0.88"},
                {"name": "Assinaturas", "value": "Presente", "confidence": "0.80"},
            ],
            "extracted_at": now,
        })
        update_item("Documents", {"document_id": doc_id}, {"status": "extracted"})

        # 4. Insights stage
        for severity, title in [("High", "Valor elevado"), ("Medium", "Prazo extenso")]:
            put_item("Insights", {
                "insight_id": str(uuid.uuid4()),
                "document_id": doc_id,
                "title": title,
                "description": f"Insight de severidade {severity}.",
                "category": "Financeiro",
                "severity": severity,
                "created_at": now,
            })

        update_item("Documents", {"document_id": doc_id}, {
            "status": "pending_review",
            "max_severity": "High",
            "processed_at": now,
        })

        # 5. Review stage
        put_item("HumanReviews", {
            "review_id": str(uuid.uuid4()),
            "document_id": doc_id,
            "reviewer_id": "analyst_01",
            "action": "approve",
            "field_name": None,
            "original_value": None,
            "new_value": None,
            "timestamp": now,
        })
        update_item("Documents", {"document_id": doc_id}, {"status": "approved"})

        # --- Verify consistency across all tables ---

        # Document final state
        doc = get_item("Documents", {"document_id": doc_id})
        assert doc["status"] == "approved"
        assert doc["category"] == "Contrato"
        assert doc["max_severity"] == "High"
        assert doc["file_name"] == "contrato_servico.pdf"

        # Extraction linked to document
        extraction = get_item("Extractions", {"document_id": doc_id})
        assert extraction is not None
        assert len(extraction["fields"]) == 4
        field_names = [f["name"] for f in extraction["fields"]]
        assert set(field_names) == {"Partes", "Valor", "Prazo", "Assinaturas"}

        # Insights linked via GSI
        insights = query_items(
            "Insights",
            key_condition={"document_id": doc_id},
            index_name="document-index",
        )
        assert len(insights) == 2
        assert {i["severity"] for i in insights} == {"High", "Medium"}

        # Reviews linked via GSI
        reviews = query_items(
            "HumanReviews",
            key_condition={"document_id": doc_id},
            index_name="document-index",
        )
        assert len(reviews) == 1
        assert reviews[0]["action"] == "approve"
        assert reviews[0]["reviewer_id"] == "analyst_01"

        # Category-index GSI
        contracts = query_items(
            "Documents",
            key_condition={"category": "Contrato"},
            index_name="category-index",
        )
        assert len(contracts) == 1
        assert contracts[0]["document_id"] == doc_id
