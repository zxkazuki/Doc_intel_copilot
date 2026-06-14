"""Tests for config module."""

import pytest

from config import Settings, get_settings


def test_settings_default_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings loads with correct defaults when env vars are not set."""
    monkeypatch.delenv("S3_BUCKET_NAME", raising=False)

    s = Settings()

    assert s.aws_region == "us-east-1"
    assert s.s3_bucket_name == "doc-intel-copilot-documents"
    assert s.s3_presigned_url_expiry == 3600
    assert s.dynamodb_documents_table == "Documents"
    assert s.dynamodb_extractions_table == "Extractions"
    assert s.dynamodb_insights_table == "Insights"
    assert s.dynamodb_reviews_table == "HumanReviews"
    assert s.bedrock_model_id == "us.anthropic.claude-sonnet-4-6"
    assert s.max_file_size_mb == 20
    assert s.allowed_formats == ["pdf", "png", "jpg", "jpeg"]
    assert s.classification_timeout == 30
    assert s.extraction_timeout == 30
    assert s.insights_timeout == 30


def test_get_settings_returns_cached_instance() -> None:
    """get_settings returns the same cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_settings_overrides_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings can be overridden via environment variables."""
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "50")

    s = Settings()

    assert s.aws_region == "eu-west-1"
    assert s.max_file_size_mb == 50
