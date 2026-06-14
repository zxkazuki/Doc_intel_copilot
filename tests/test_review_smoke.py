"""Smoke test for review module — validates basic functionality with moto."""

import boto3
import pytest
from moto import mock_aws

from modules.review import (
    FieldCorrection,
    ReviewAction,
    approve_document,
    correct_field,
    reject_document,
)
from config import get_settings


@pytest.fixture
def dynamodb_tables():
    """Create mocked DynamoDB tables for testing."""
    with mock_aws():
        settings = get_settings()
        ddb = boto3.resource("dynamodb", region_name=settings.aws_region)

        ddb.create_table(
            TableName=settings.dynamodb_documents_table,
            KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "document_id", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        ddb.create_table(
            TableName=settings.dynamodb_reviews_table,
            KeySchema=[
                {"AttributeName": "review_id", "KeyType": "HASH"},
                {"AttributeName": "document_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "review_id", "AttributeType": "S"},
                {"AttributeName": "document_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        docs_table = ddb.Table(settings.dynamodb_documents_table)
        docs_table.put_item(
            Item={"document_id": "doc-123", "status": "pending_review"}
        )

        yield ddb


def test_approve_document(dynamodb_tables):
    settings = get_settings()
    result = approve_document("doc-123", "reviewer-A")

    assert result is True

    doc = dynamodb_tables.Table(settings.dynamodb_documents_table).get_item(
        Key={"document_id": "doc-123"}
    )["Item"]
    assert doc["status"] == "approved"

    reviews = dynamodb_tables.Table(settings.dynamodb_reviews_table).scan()["Items"]
    assert len(reviews) == 1
    review = reviews[0]
    assert review["document_id"] == "doc-123"
    assert review["reviewer_id"] == "reviewer-A"
    assert review["action"] == "approve"
    assert "review_id" in review
    assert "timestamp" in review


def test_reject_document(dynamodb_tables):
    settings = get_settings()
    result = reject_document("doc-123", "reviewer-B")

    assert result is True

    doc = dynamodb_tables.Table(settings.dynamodb_documents_table).get_item(
        Key={"document_id": "doc-123"}
    )["Item"]
    assert doc["status"] == "rejected"

    reviews = dynamodb_tables.Table(settings.dynamodb_reviews_table).scan()["Items"]
    assert len(reviews) == 1
    assert reviews[0]["action"] == "reject"
    assert reviews[0]["reviewer_id"] == "reviewer-B"


def test_correct_field(dynamodb_tables):
    settings = get_settings()
    correction = FieldCorrection(
        field_name="CPF",
        original_value="123.456.789-00",
        corrected_value="987.654.321-00",
    )

    result = correct_field("doc-123", "reviewer-C", correction)

    assert result is True

    reviews = dynamodb_tables.Table(settings.dynamodb_reviews_table).scan()["Items"]
    assert len(reviews) == 1
    review = reviews[0]
    assert review["action"] == "correction"
    assert review["field_name"] == "CPF"
    assert review["original_value"] == "123.456.789-00"
    assert review["new_value"] == "987.654.321-00"
    assert review["reviewer_id"] == "reviewer-C"
    assert "review_id" in review
    assert "timestamp" in review


def test_correct_field_with_null_original(dynamodb_tables):
    settings = get_settings()
    correction = FieldCorrection(
        field_name="Telefone",
        original_value=None,
        corrected_value="(11) 99999-0000",
    )

    result = correct_field("doc-123", "reviewer-D", correction)

    assert result is True

    reviews = dynamodb_tables.Table(settings.dynamodb_reviews_table).scan()["Items"]
    assert len(reviews) == 1
    review = reviews[0]
    assert review["field_name"] == "Telefone"
    assert review.get("original_value") is None
    assert review["new_value"] == "(11) 99999-0000"


def test_approve_returns_false_on_dynamo_error():
    """Without tables, DynamoDB calls fail — function returns False."""
    with mock_aws():
        result = approve_document("nonexistent-doc", "reviewer-X")
        assert result is False


def test_reject_returns_false_on_dynamo_error():
    with mock_aws():
        result = reject_document("nonexistent-doc", "reviewer-X")
        assert result is False


def test_correct_field_returns_false_on_dynamo_error():
    with mock_aws():
        correction = FieldCorrection(
            field_name="Nome", original_value="A", corrected_value="B"
        )
        result = correct_field("nonexistent-doc", "reviewer-X", correction)
        assert result is False
