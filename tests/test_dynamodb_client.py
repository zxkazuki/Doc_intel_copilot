"""Tests for infrastructure/dynamodb_client.py."""

from decimal import Decimal

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

TABLE_NAME = "TestTable"
GSI_TABLE_NAME = "TestGSITable"


@pytest.fixture
def dynamodb_table():
    """Creates a mock DynamoDB table with a simple PK."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


@pytest.fixture
def dynamodb_table_with_sk():
    """Creates a mock DynamoDB table with PK + SK and a GSI."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=GSI_TABLE_NAME,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "uploaded_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "status-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "uploaded_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


class TestPutItem:
    def test_inserts_item(self, dynamodb_table):
        put_item(TABLE_NAME, {"pk": "doc-001", "name": "test.pdf", "size": 1024})

        result = get_item(TABLE_NAME, {"pk": "doc-001"})
        assert result is not None
        assert result["name"] == "test.pdf"
        assert result["size"] == 1024

    def test_overwrites_existing_item(self, dynamodb_table):
        put_item(TABLE_NAME, {"pk": "doc-001", "name": "old.pdf"})
        put_item(TABLE_NAME, {"pk": "doc-001", "name": "new.pdf"})

        result = get_item(TABLE_NAME, {"pk": "doc-001"})
        assert result["name"] == "new.pdf"


class TestGetItem:
    def test_returns_none_for_nonexistent_key(self, dynamodb_table):
        assert get_item(TABLE_NAME, {"pk": "nonexistent"}) is None

    def test_returns_item_when_exists(self, dynamodb_table):
        put_item(TABLE_NAME, {"pk": "doc-002", "status": "uploaded"})

        result = get_item(TABLE_NAME, {"pk": "doc-002"})
        assert result["status"] == "uploaded"


class TestUpdateItem:
    def test_updates_single_field(self, dynamodb_table):
        put_item(TABLE_NAME, {"pk": "doc-003", "status": "uploaded"})
        update_item(TABLE_NAME, {"pk": "doc-003"}, {"status": "classified"})

        assert get_item(TABLE_NAME, {"pk": "doc-003"})["status"] == "classified"

    def test_updates_multiple_fields(self, dynamodb_table):
        put_item(TABLE_NAME, {"pk": "doc-004", "status": "uploaded"})
        update_item(
            TABLE_NAME,
            {"pk": "doc-004"},
            {"status": "classified", "category": "Contrato", "confidence": Decimal("0.95")},
        )

        result = get_item(TABLE_NAME, {"pk": "doc-004"})
        assert result["status"] == "classified"
        assert result["category"] == "Contrato"
        assert result["confidence"] == Decimal("0.95")

    def test_noop_when_updates_empty(self, dynamodb_table):
        put_item(TABLE_NAME, {"pk": "doc-005", "status": "uploaded"})
        update_item(TABLE_NAME, {"pk": "doc-005"}, {})

        assert get_item(TABLE_NAME, {"pk": "doc-005"})["status"] == "uploaded"


class TestQueryItems:
    def test_by_partition_key(self, dynamodb_table_with_sk):
        put_item(GSI_TABLE_NAME, {"pk": "doc-1", "sk": "2024-01-01", "status": "uploaded", "uploaded_at": "2024-01-01"})
        put_item(GSI_TABLE_NAME, {"pk": "doc-1", "sk": "2024-01-02", "status": "classified", "uploaded_at": "2024-01-02"})
        put_item(GSI_TABLE_NAME, {"pk": "doc-2", "sk": "2024-01-01", "status": "uploaded", "uploaded_at": "2024-01-01"})

        results = query_items(GSI_TABLE_NAME, key_condition={"pk": "doc-1"})
        assert len(results) == 2

    def test_sort_key_begins_with(self, dynamodb_table_with_sk):
        put_item(GSI_TABLE_NAME, {"pk": "doc-1", "sk": "2024-01-01", "status": "a", "uploaded_at": "x"})
        put_item(GSI_TABLE_NAME, {"pk": "doc-1", "sk": "2024-02-01", "status": "b", "uploaded_at": "y"})

        results = query_items(
            GSI_TABLE_NAME,
            key_condition={"pk": "doc-1", "sk": {"begins_with": "2024-01"}},
        )
        assert len(results) == 1
        assert results[0]["sk"] == "2024-01-01"

    def test_gsi_query(self, dynamodb_table_with_sk):
        put_item(GSI_TABLE_NAME, {"pk": "d1", "sk": "a", "status": "uploaded", "uploaded_at": "2024-01-01"})
        put_item(GSI_TABLE_NAME, {"pk": "d2", "sk": "b", "status": "uploaded", "uploaded_at": "2024-01-02"})
        put_item(GSI_TABLE_NAME, {"pk": "d3", "sk": "c", "status": "classified", "uploaded_at": "2024-01-03"})

        results = query_items(
            GSI_TABLE_NAME,
            key_condition={"status": "uploaded"},
            index_name="status-index",
        )
        assert len(results) == 2
        assert all(r["status"] == "uploaded" for r in results)

    def test_with_limit(self, dynamodb_table_with_sk):
        for i in range(5):
            put_item(GSI_TABLE_NAME, {"pk": "doc-1", "sk": f"2024-01-0{i+1}", "status": "x", "uploaded_at": f"0{i}"})

        results = query_items(GSI_TABLE_NAME, key_condition={"pk": "doc-1"}, limit=2)
        assert len(results) == 2

    def test_with_filter_expression(self, dynamodb_table_with_sk):
        put_item(GSI_TABLE_NAME, {"pk": "doc-1", "sk": "a", "status": "x", "uploaded_at": "1", "category": "Contrato"})
        put_item(GSI_TABLE_NAME, {"pk": "doc-1", "sk": "b", "status": "x", "uploaded_at": "2", "category": "Laudo"})

        results = query_items(
            GSI_TABLE_NAME,
            key_condition={"pk": "doc-1"},
            filter_expr={"category": "Contrato"},
        )
        assert len(results) == 1
        assert results[0]["category"] == "Contrato"

    def test_scan_forward_ordering(self, dynamodb_table_with_sk):
        put_item(GSI_TABLE_NAME, {"pk": "doc-1", "sk": "a", "status": "x", "uploaded_at": "1"})
        put_item(GSI_TABLE_NAME, {"pk": "doc-1", "sk": "b", "status": "x", "uploaded_at": "2"})
        put_item(GSI_TABLE_NAME, {"pk": "doc-1", "sk": "c", "status": "x", "uploaded_at": "3"})

        asc = query_items(GSI_TABLE_NAME, key_condition={"pk": "doc-1"}, scan_forward=True)
        desc = query_items(GSI_TABLE_NAME, key_condition={"pk": "doc-1"}, scan_forward=False)

        assert asc[0]["sk"] == "a"
        assert desc[0]["sk"] == "c"


class TestScanItems:
    def test_scans_all_items(self, dynamodb_table):
        for i in range(3):
            put_item(TABLE_NAME, {"pk": f"doc-{i}", "status": "uploaded"})

        result = scan_items(TABLE_NAME)
        assert len(result["items"]) == 3
        assert result["last_evaluated_key"] is None

    def test_with_equality_filter(self, dynamodb_table):
        put_item(TABLE_NAME, {"pk": "doc-1", "status": "uploaded"})
        put_item(TABLE_NAME, {"pk": "doc-2", "status": "classified"})
        put_item(TABLE_NAME, {"pk": "doc-3", "status": "uploaded"})

        result = scan_items(TABLE_NAME, filter_expr={"status": "uploaded"})
        assert len(result["items"]) == 2

    def test_with_limit(self, dynamodb_table):
        for i in range(5):
            put_item(TABLE_NAME, {"pk": f"doc-{i}"})

        result = scan_items(TABLE_NAME, limit=2)
        assert len(result["items"]) == 2

    def test_with_contains_filter(self, dynamodb_table):
        put_item(TABLE_NAME, {"pk": "doc-1", "file_name": "relatorio_vendas.pdf"})
        put_item(TABLE_NAME, {"pk": "doc-2", "file_name": "contrato_aluguel.pdf"})
        put_item(TABLE_NAME, {"pk": "doc-3", "file_name": "relatorio_mensal.pdf"})

        result = scan_items(TABLE_NAME, filter_expr={"file_name": {"contains": "relatorio"}})
        assert len(result["items"]) == 2
