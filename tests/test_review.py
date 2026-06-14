"""Property-based tests for review module — Properties 11 and 12.

# Feature: document-intelligence-copilot, Property 11: Review actions produce complete audit records
# Feature: document-intelligence-copilot, Property 12: Review state transitions are correct
"""

import boto3
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from config import get_settings
from modules.review import (
    FieldCorrection,
    ReviewAction,
    approve_document,
    correct_field,
    reject_document,
)

# --- Hypothesis Strategies ---

reviewer_ids = st.text(
    min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))
)

field_names = st.text(
    min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))
)

field_values = st.text(min_size=1, max_size=200)

field_corrections = st.builds(
    FieldCorrection,
    field_name=field_names,
    original_value=st.one_of(st.none(), field_values),
    corrected_value=field_values,
)

DOC_ID = "prop-doc-001"


def setup_tables():
    """Create mocked DynamoDB tables and seed a pending_review document."""
    conf = get_settings()
    ddb = boto3.resource("dynamodb", region_name=conf.aws_region)

    ddb.create_table(
        TableName=conf.dynamodb_documents_table,
        KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "document_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName=conf.dynamodb_reviews_table,
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

    ddb.Table(conf.dynamodb_documents_table).put_item(
        Item={"document_id": DOC_ID, "status": "pending_review"}
    )
    return ddb


# --- Property 11: Review actions produce complete audit records ---
# **Validates: Requirements 5.3, 5.6**


class TestProperty11AuditRecordCompleteness:
    """For any review action, the HumanReviews entry SHALL contain non-null:
    review_id, document_id, reviewer_id, action, timestamp.
    For corrections: field_name, new_value also non-null.
    """

    @settings(max_examples=20, deadline=None)
    @given(reviewer_id=reviewer_ids)
    def test_approve_audit_record_complete(self, reviewer_id: str):
        with mock_aws():
            setup_tables()
            assert approve_document(DOC_ID, reviewer_id) is True

            conf = get_settings()
            items = boto3.resource("dynamodb", region_name=conf.aws_region).Table(
                conf.dynamodb_reviews_table
            ).scan()["Items"]

            assert len(items) == 1
            review = items[0]
            assert review["review_id"] is not None
            assert review["document_id"] == DOC_ID
            assert review["reviewer_id"] == reviewer_id
            assert review["action"] == ReviewAction.APPROVE
            assert review["timestamp"] is not None

    @settings(max_examples=20, deadline=None)
    @given(reviewer_id=reviewer_ids)
    def test_reject_audit_record_complete(self, reviewer_id: str):
        with mock_aws():
            setup_tables()
            assert reject_document(DOC_ID, reviewer_id) is True

            conf = get_settings()
            items = boto3.resource("dynamodb", region_name=conf.aws_region).Table(
                conf.dynamodb_reviews_table
            ).scan()["Items"]

            assert len(items) == 1
            review = items[0]
            assert review["review_id"] is not None
            assert review["document_id"] == DOC_ID
            assert review["reviewer_id"] == reviewer_id
            assert review["action"] == ReviewAction.REJECT
            assert review["timestamp"] is not None

    @settings(max_examples=20, deadline=None)
    @given(reviewer_id=reviewer_ids, correction=field_corrections)
    def test_correction_audit_record_complete(
        self, reviewer_id: str, correction: FieldCorrection
    ):
        with mock_aws():
            setup_tables()
            assert correct_field(DOC_ID, reviewer_id, correction) is True

            conf = get_settings()
            items = boto3.resource("dynamodb", region_name=conf.aws_region).Table(
                conf.dynamodb_reviews_table
            ).scan()["Items"]

            assert len(items) == 1
            review = items[0]
            assert review["review_id"] is not None
            assert review["document_id"] == DOC_ID
            assert review["reviewer_id"] == reviewer_id
            assert review["action"] == ReviewAction.CORRECTION
            assert review["timestamp"] is not None
            # Correction-specific fields
            assert review["field_name"] == correction.field_name
            assert review["new_value"] == correction.corrected_value
            assert review.get("original_value") == correction.original_value


# --- Property 12: Review state transitions are correct ---
# **Validates: Requirements 5.4, 5.5**


class TestProperty12StateTransitions:
    """approve_document → status='approved', reject_document → status='rejected'.
    No other values allowed.
    """

    @settings(max_examples=20, deadline=None)
    @given(reviewer_id=reviewer_ids)
    def test_approve_transitions_to_approved(self, reviewer_id: str):
        with mock_aws():
            setup_tables()
            assert approve_document(DOC_ID, reviewer_id) is True

            conf = get_settings()
            doc = boto3.resource("dynamodb", region_name=conf.aws_region).Table(
                conf.dynamodb_documents_table
            ).get_item(Key={"document_id": DOC_ID})["Item"]
            assert doc["status"] == "approved"

    @settings(max_examples=20, deadline=None)
    @given(reviewer_id=reviewer_ids)
    def test_reject_transitions_to_rejected(self, reviewer_id: str):
        with mock_aws():
            setup_tables()
            assert reject_document(DOC_ID, reviewer_id) is True

            conf = get_settings()
            doc = boto3.resource("dynamodb", region_name=conf.aws_region).Table(
                conf.dynamodb_documents_table
            ).get_item(Key={"document_id": DOC_ID})["Item"]
            assert doc["status"] == "rejected"
