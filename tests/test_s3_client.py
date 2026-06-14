"""Unit tests for infrastructure/s3_client.py."""

import boto3
import pytest
from moto import mock_aws
from unittest.mock import patch

from config import get_settings
from infrastructure.s3_client import download_file, generate_presigned_url, upload_file


@pytest.fixture
def mock_s3():
    """Provide a mocked S3 environment with the configured bucket created."""
    with mock_aws():
        settings = get_settings()
        client = boto3.client("s3", region_name=settings.aws_region)
        client.create_bucket(Bucket=settings.s3_bucket_name)
        yield client


class TestUploadFile:
    def test_upload_success(self, mock_s3):
        content = b"hello world pdf content"
        key = "documents/test-file.pdf"

        result = upload_file(content, key, "application/pdf")

        assert result is True
        obj = mock_s3.get_object(Bucket=get_settings().s3_bucket_name, Key=key)
        assert obj["Body"].read() == content
        assert obj["ContentType"] == "application/pdf"

    def test_upload_connection_error_returns_false(self):
        with patch("infrastructure.s3_client._get_s3_client") as mock_client:
            mock_client.return_value.put_object.side_effect = ConnectionError("Network error")
            assert upload_file(b"data", "key.pdf", "application/pdf") is False


class TestDownloadFile:
    def test_download_success(self, mock_s3):
        content = b"downloaded content here"
        key = "documents/download-test.pdf"
        mock_s3.put_object(Bucket=get_settings().s3_bucket_name, Key=key, Body=content)

        assert download_file(key) == content

    def test_download_nonexistent_key_returns_empty(self, mock_s3):
        assert download_file("nonexistent/key.pdf") == b""

    def test_download_connection_error_returns_empty(self):
        with patch("infrastructure.s3_client._get_s3_client") as mock_client:
            mock_client.return_value.get_object.side_effect = ConnectionError("Network error")
            assert download_file("any-key.pdf") == b""


class TestGeneratePresignedUrl:
    def test_presigned_url_contains_key(self, mock_s3):
        key = "documents/presigned-test.pdf"
        url = generate_presigned_url(key)

        assert url != ""
        assert "presigned-test.pdf" in url

    def test_presigned_url_with_custom_expiry(self, mock_s3):
        url = generate_presigned_url("documents/expiry-test.pdf", expiry=600)
        assert url != ""

    def test_presigned_url_uses_default_expiry(self, mock_s3):
        url = generate_presigned_url("documents/default-expiry.pdf")
        assert url != ""

    def test_presigned_url_connection_error_returns_empty(self):
        with patch("infrastructure.s3_client._get_s3_client") as mock_client:
            mock_client.return_value.generate_presigned_url.side_effect = ConnectionError(
                "Network error"
            )
            assert generate_presigned_url("any-key.pdf") == ""
