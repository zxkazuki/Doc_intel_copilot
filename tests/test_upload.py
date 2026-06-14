"""Unit tests for modules/upload.py — file validation and upload logic."""

import boto3
import pytest
from moto import mock_aws
from unittest.mock import patch

from modules.upload import ValidationResult, UploadResult, validate_file, upload_document


MAX_SIZE = 20 * 1024 * 1024  # 20 MB in bytes


class TestValidateFileFormat:
    """Tests for file format validation."""

    @pytest.mark.parametrize("ext", ["pdf", "png", "jpg", "jpeg"])
    def test_valid_extensions_lowercase(self, ext: str) -> None:
        result = validate_file(f"document.{ext}", 1024)
        assert result.valid is True
        assert result.error_message is None

    @pytest.mark.parametrize("ext", ["PDF", "PNG", "JPG", "JPEG"])
    def test_valid_extensions_uppercase(self, ext: str) -> None:
        result = validate_file(f"document.{ext}", 1024)
        assert result.valid is True
        assert result.error_message is None

    @pytest.mark.parametrize("ext", ["Pdf", "pNg", "JpG", "JpEg"])
    def test_valid_extensions_mixed_case(self, ext: str) -> None:
        result = validate_file(f"document.{ext}", 1024)
        assert result.valid is True
        assert result.error_message is None

    @pytest.mark.parametrize("ext", ["doc", "xls", "txt", "docx", "bmp", "gif"])
    def test_invalid_extensions(self, ext: str) -> None:
        result = validate_file(f"document.{ext}", 1024)
        assert result.valid is False
        assert "Formato não suportado" in result.error_message
        assert "PDF, PNG, JPG, JPEG" in result.error_message

    def test_no_extension(self) -> None:
        result = validate_file("document_without_ext", 1024)
        assert result.valid is False
        assert "Formato não suportado" in result.error_message


class TestValidateFileSize:
    """Tests for file size validation."""

    def test_size_exactly_at_limit(self) -> None:
        result = validate_file("file.pdf", MAX_SIZE)
        assert result.valid is True

    def test_size_one_byte_over_limit(self) -> None:
        result = validate_file("file.pdf", MAX_SIZE + 1)
        assert result.valid is False
        assert "tamanho máximo" in result.error_message
        assert "20 MB" in result.error_message

    def test_size_zero_bytes(self) -> None:
        result = validate_file("file.pdf", 0)
        assert result.valid is True

    def test_size_well_under_limit(self) -> None:
        result = validate_file("file.png", 1_000_000)
        assert result.valid is True

    def test_size_well_over_limit(self) -> None:
        result = validate_file("file.jpg", 30 * 1024 * 1024)
        assert result.valid is False


class TestValidateFileCombined:
    """Tests combining format and size validation."""

    def test_invalid_format_takes_precedence_over_size(self) -> None:
        result = validate_file("file.doc", MAX_SIZE + 1)
        assert result.valid is False
        assert "Formato não suportado" in result.error_message


class TestDataclasses:
    """Tests for dataclass structure."""

    def test_validation_result_defaults(self) -> None:
        r = ValidationResult(valid=True)
        assert r.error_message is None

    def test_upload_result_defaults(self) -> None:
        r = UploadResult(success=True)
        assert r.document_id is None
        assert r.error_message is None


# Feature: document-intelligence-copilot, Property 1: File validation accepts only valid formats and sizes

from hypothesis import given, settings, assume
from hypothesis import strategies as st


VALID_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

# --- Strategies ---
valid_file_names = st.from_regex(
    r"[a-zA-Z0-9_-]{1,50}\.(pdf|png|jpg|jpeg|PDF|PNG|JPG|JPEG)",
    fullmatch=True,
)
invalid_file_names = st.from_regex(
    r"[a-zA-Z0-9_-]{1,50}\.(doc|xls|txt|docx|bmp|gif|pptx|csv|xml|html)",
    fullmatch=True,
)
valid_sizes = st.integers(min_value=0, max_value=MAX_FILE_SIZE)
oversized = st.integers(min_value=MAX_FILE_SIZE + 1, max_value=30 * 1024 * 1024)
all_file_names = st.from_regex(
    r"[a-zA-Z0-9_-]{1,50}\.(pdf|png|jpg|jpeg|doc|xls|txt|docx|bmp|gif)",
    fullmatch=True,
)
all_file_sizes = st.integers(min_value=0, max_value=30 * 1024 * 1024)


class TestFileValidationProperty:
    """
    Property 1: File validation accepts only valid formats and sizes.

    **Validates: Requirements 1.1, 1.4, 1.6**
    """

    @given(file_name=valid_file_names, file_size=valid_sizes)
    @settings(max_examples=100)
    def test_valid_format_and_size_returns_true(self, file_name: str, file_size: int) -> None:
        """Valid extension + size ≤ 20MB → valid=True."""
        result = validate_file(file_name, file_size)
        assert result.valid is True
        assert result.error_message is None

    @given(file_name=invalid_file_names, file_size=all_file_sizes)
    @settings(max_examples=100)
    def test_invalid_format_returns_false(self, file_name: str, file_size: int) -> None:
        """Invalid extension → valid=False with format error."""
        result = validate_file(file_name, file_size)
        assert result.valid is False
        assert "Formato não suportado" in result.error_message

    @given(file_name=valid_file_names, file_size=oversized)
    @settings(max_examples=100)
    def test_oversized_returns_false(self, file_name: str, file_size: int) -> None:
        """Valid extension but size > 20MB → valid=False with size error."""
        result = validate_file(file_name, file_size)
        assert result.valid is False
        assert "tamanho máximo" in result.error_message

    @given(file_name=all_file_names, file_size=all_file_sizes)
    @settings(max_examples=200)
    def test_biconditional_valid_iff_correct_ext_and_size(
        self, file_name: str, file_size: int
    ) -> None:
        """Universal: valid=True ↔ extension ∈ {pdf,png,jpg,jpeg} AND size ≤ 20MB."""
        extension = file_name.rsplit(".", 1)[-1].lower()
        expected_valid = extension in VALID_EXTENSIONS and file_size <= MAX_FILE_SIZE

        result = validate_file(file_name, file_size)
        assert result.valid is expected_valid

        if not result.valid:
            if extension not in VALID_EXTENSIONS:
                assert "Formato não suportado" in result.error_message
            else:
                assert "tamanho máximo" in result.error_message



def _setup_aws():
    """Create mocked S3 bucket and DynamoDB Documents table."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.create_table(
        TableName="Documents",
        KeySchema=[{"AttributeName": "document_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "document_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    return s3, table


class TestUploadDocument:
    """Tests for upload_document function."""

    @mock_aws
    def test_successful_upload(self) -> None:
        _setup_aws()
        result = upload_document(b"fake pdf content", "report.pdf", 1024)

        assert result.success is True
        assert result.document_id is not None
        assert result.error_message is None

    def test_invalid_format_returns_validation_error(self) -> None:
        result = upload_document(b"content", "file.doc", 1024)

        assert result.success is False
        assert "Formato não suportado" in result.error_message
        assert result.document_id is None

    def test_oversized_file_returns_validation_error(self) -> None:
        result = upload_document(b"x", "file.pdf", 30 * 1024 * 1024)

        assert result.success is False
        assert "tamanho máximo" in result.error_message

    def test_s3_failure_returns_error(self) -> None:
        with patch("modules.upload.upload_file", return_value=False):
            result = upload_document(b"content", "doc.pdf", 100)

        assert result.success is False
        assert "Falha ao enviar arquivo" in result.error_message
        assert result.document_id is None

    def test_dynamodb_failure_returns_error(self) -> None:
        with patch("modules.upload.upload_file", return_value=True):
            with patch("modules.upload.put_item", side_effect=Exception("DB error")):
                result = upload_document(b"content", "doc.pdf", 100)

        assert result.success is False
        assert "Falha ao registrar documento" in result.error_message

    @mock_aws
    def test_s3_key_format(self) -> None:
        s3, _ = _setup_aws()
        result = upload_document(b"png content", "image.png", 500)

        assert result.success is True
        objects = s3.list_objects_v2(Bucket="test-bucket")
        keys = [obj["Key"] for obj in objects.get("Contents", [])]
        assert len(keys) == 1
        assert keys[0].startswith("documents/")
        assert keys[0].endswith(".png")

    @mock_aws
    def test_dynamodb_record_metadata(self) -> None:
        _, table = _setup_aws()
        result = upload_document(b"jpeg content", "photo.jpeg", 2048)

        assert result.success is True
        item = table.get_item(Key={"document_id": result.document_id})["Item"]
        assert item["file_name"] == "photo.jpeg"
        assert item["file_format"] == "jpeg"
        assert item["file_size_bytes"] == 2048
        assert item["s3_key"].startswith("documents/")
        assert item["s3_key"].endswith(".jpeg")
        assert item["status"] == "uploaded"
        assert "uploaded_at" in item
