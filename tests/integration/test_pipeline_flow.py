"""Integration tests for the complete document processing pipeline.

Tests the full flow: upload → classify → extract → insights
with mocked AWS services (moto) and mocked Bedrock responses.

Validates:
- Requirements 1.2, 1.3: Upload stores in S3 and DynamoDB
- Requirements 2.1: Classification via Bedrock
- Requirements 3.1: Extraction via Bedrock
- Requirements 4.1: Insights generation via Bedrock
- Requirements 5.9: Document reaches pending_review status
"""

import boto3
import pytest
from moto import mock_aws
from unittest.mock import patch

from modules.upload import upload_document
from modules.classifier import classify_document
from modules.extractor import extract_fields
from modules.insights import generate_insights


# --- Controlled Bedrock responses ---

CLASSIFICATION_RESPONSE = {
    "category": "Contrato",
    "confidence": 0.92,
}

EXTRACTION_RESPONSE = {
    "fields": [
        {"name": "Partes", "value": "Empresa ABC e João Silva", "confidence": 0.95},
        {"name": "Valor", "value": "R$ 50.000,00", "confidence": 0.88},
        {"name": "Prazo", "value": "12 meses", "confidence": 0.91},
        {"name": "Assinaturas", "value": "Presentes", "confidence": 0.85},
    ]
}

INSIGHTS_RESPONSE = {
    "insights": [
        {
            "title": "Contrato com valor elevado",
            "description": "O valor do contrato excede R$ 30.000. Recomenda-se revisão jurídica.",
            "category": "Financeiro",
            "severity": "Medium",
        },
        {
            "title": "Prazo dentro do padrão",
            "description": "O prazo de 12 meses está dentro dos parâmetros normais.",
            "category": "Operacional",
            "severity": "Low",
        },
    ]
}


# --- Setup helpers ---


def _setup_aws():
    """Create all mocked AWS resources: S3 bucket + DynamoDB tables."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

    dynamodb.create_table(
        TableName="Documents",
        KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "document_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    dynamodb.create_table(
        TableName="Extractions",
        KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "document_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    dynamodb.create_table(
        TableName="Insights",
        KeySchema=[
            {"AttributeName": "insight_id", "KeyType": "HASH"},
            {"AttributeName": "document_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "insight_id", "AttributeType": "S"},
            {"AttributeName": "document_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    return s3, dynamodb


def _run_full_pipeline(file_bytes: bytes, file_name: str) -> str:
    """Run the full pipeline and return the document_id."""
    result = upload_document(file_bytes, file_name, len(file_bytes))
    assert result.success is True
    doc_id = result.document_id

    with patch("modules.classifier.invoke_claude_json", return_value=CLASSIFICATION_RESPONSE):
        classify_document(doc_id)

    with patch("modules.extractor.invoke_claude_json", return_value=EXTRACTION_RESPONSE):
        extract_fields(doc_id)

    with patch("modules.insights.invoke_claude_json", return_value=INSIGHTS_RESPONSE):
        generate_insights(doc_id)

    return doc_id


# --- Integration Tests ---


class TestCompletePipelineHappyPath:
    """Full pipeline from upload to insights succeeds end-to-end."""

    @mock_aws
    def test_complete_pipeline_happy_path(self) -> None:
        _setup_aws()
        file_bytes = b"%PDF-1.4 fake pdf content for testing"

        # Upload
        upload_result = upload_document(file_bytes, "contrato_teste.pdf", len(file_bytes))
        assert upload_result.success is True
        doc_id = upload_result.document_id

        # Classify
        with patch("modules.classifier.invoke_claude_json", return_value=CLASSIFICATION_RESPONSE):
            classification_result = classify_document(doc_id)
        assert classification_result.success is True
        assert classification_result.category == "Contrato"
        assert classification_result.confidence == 0.92

        # Extract
        with patch("modules.extractor.invoke_claude_json", return_value=EXTRACTION_RESPONSE):
            extraction_result = extract_fields(doc_id)
        assert extraction_result.success is True
        assert len(extraction_result.fields) == 4
        assert {f.name for f in extraction_result.fields} == {"Partes", "Valor", "Prazo", "Assinaturas"}

        # Insights
        with patch("modules.insights.invoke_claude_json", return_value=INSIGHTS_RESPONSE):
            insights_result = generate_insights(doc_id)
        assert insights_result.success is True
        assert len(insights_result.insights) == 2

        # Final document status
        table = boto3.resource("dynamodb", region_name="us-east-1").Table("Documents")
        doc = table.get_item(Key={"document_id": doc_id})["Item"]
        assert doc["status"] == "pending_review"
        assert doc["max_severity"] == "Medium"
        assert "processed_at" in doc


class TestPipelineStateTransitions:
    """Verify each status change in sequence through the pipeline."""

    @mock_aws
    def test_pipeline_state_transitions(self) -> None:
        _setup_aws()
        doc_table = boto3.resource("dynamodb", region_name="us-east-1").Table("Documents")
        file_bytes = b"%PDF-1.4 contract document"

        # Upload → "uploaded"
        upload_result = upload_document(file_bytes, "contract.pdf", len(file_bytes))
        doc_id = upload_result.document_id
        doc = doc_table.get_item(Key={"document_id": doc_id})["Item"]
        assert doc["status"] == "uploaded"

        # Classify → "classified"
        with patch("modules.classifier.invoke_claude_json", return_value=CLASSIFICATION_RESPONSE):
            classify_document(doc_id)
        doc = doc_table.get_item(Key={"document_id": doc_id})["Item"]
        assert doc["status"] == "classified"
        assert doc["category"] == "Contrato"
        assert doc["classification_confidence"] == "0.92"

        # Extract → "extracted"
        with patch("modules.extractor.invoke_claude_json", return_value=EXTRACTION_RESPONSE):
            extract_fields(doc_id)
        doc = doc_table.get_item(Key={"document_id": doc_id})["Item"]
        assert doc["status"] == "extracted"

        # Insights → "pending_review"
        with patch("modules.insights.invoke_claude_json", return_value=INSIGHTS_RESPONSE):
            generate_insights(doc_id)
        doc = doc_table.get_item(Key={"document_id": doc_id})["Item"]
        assert doc["status"] == "pending_review"


class TestPipelineDataPersistence:
    """Verify all tables have correct data after full pipeline flow."""

    @mock_aws
    def test_pipeline_data_persistence(self) -> None:
        _setup_aws()
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        file_bytes = b"%PDF-1.4 nota fiscal content"

        doc_id = _run_full_pipeline(file_bytes, "nota_fiscal.pdf")

        # Verify Documents table
        doc = dynamodb.Table("Documents").get_item(Key={"document_id": doc_id})["Item"]
        assert doc["file_name"] == "nota_fiscal.pdf"
        assert doc["file_format"] == "pdf"
        assert doc["file_size_bytes"] == len(file_bytes)
        assert doc["s3_key"].startswith("documents/")
        assert doc["s3_key"].endswith(".pdf")
        assert doc["status"] == "pending_review"
        assert doc["category"] == "Contrato"
        assert "uploaded_at" in doc
        assert "processed_at" in doc
        assert doc["max_severity"] == "Medium"

        # Verify Extractions table
        extraction = dynamodb.Table("Extractions").get_item(Key={"document_id": doc_id})["Item"]
        assert extraction["document_id"] == doc_id
        assert "extracted_at" in extraction
        assert len(extraction["fields"]) == 4
        field_names = {f["name"] for f in extraction["fields"]}
        assert field_names == {"Partes", "Valor", "Prazo", "Assinaturas"}

        # Verify Insights table
        scan_result = dynamodb.Table("Insights").scan()
        insight_items = [i for i in scan_result["Items"] if i["document_id"] == doc_id]
        assert len(insight_items) == 2
        for item in insight_items:
            assert "insight_id" in item
            assert item["document_id"] == doc_id
            assert item["category"] in {"Financeiro", "Operacional", "Compliance", "Qualidade"}
            assert item["severity"] in {"Low", "Medium", "High", "Critical"}
            assert "created_at" in item

        # Verify S3 has the file
        s3 = boto3.client("s3", region_name="us-east-1")
        s3_obj = s3.get_object(Bucket="test-bucket", Key=doc["s3_key"])
        assert s3_obj["Body"].read() == file_bytes
