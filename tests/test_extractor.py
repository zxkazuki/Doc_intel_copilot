"""Unit tests for modules/extractor.py — structured field extraction logic.

Tests extraction for each category, generic document truncation,
missing field handling, and error scenarios.

Requirements: 3.2, 3.7, 3.9
"""

from unittest.mock import patch

import pytest

from modules.extractor import (
    ExtractedField,
    ExtractionResult,
    extract_fields,
    _parse_extraction_response,
    _clamp_confidence,
    _get_media_type,
)
from prompts.extraction import EXTRACTION_SCHEMAS


# ---------------------------------------------------------------------------
# Tests for _get_media_type helper
# ---------------------------------------------------------------------------


class TestGetMediaType:
    @pytest.mark.parametrize(
        "file_format,expected",
        [
            ("pdf", "application/pdf"),
            ("png", "image/png"),
            ("jpg", "image/jpeg"),
            ("jpeg", "image/jpeg"),
            ("PDF", "application/pdf"),
        ],
    )
    def test_known_formats(self, file_format: str, expected: str) -> None:
        assert _get_media_type(file_format) == expected

    def test_unknown_format_returns_octet_stream(self) -> None:
        assert _get_media_type("doc") == "application/octet-stream"


# ---------------------------------------------------------------------------
# Tests for _clamp_confidence helper
# ---------------------------------------------------------------------------


class TestClampConfidence:
    def test_normal_value(self) -> None:
        assert _clamp_confidence(0.85) == 0.85

    def test_above_one_clamped(self) -> None:
        assert _clamp_confidence(1.5) == 1.0

    def test_below_zero_clamped(self) -> None:
        assert _clamp_confidence(-0.3) == 0.0

    def test_non_numeric_returns_zero(self) -> None:
        assert _clamp_confidence("invalid") == 0.0

    def test_none_returns_zero(self) -> None:
        assert _clamp_confidence(None) == 0.0


# ---------------------------------------------------------------------------
# Tests for _parse_extraction_response (Requirement 3.2, 3.7, 3.9)
# ---------------------------------------------------------------------------


class TestParseExtractionResponse:
    def test_contrato_all_fields_present(self) -> None:
        """Contrato with all 4 fields returned."""
        response = {
            "fields": [
                {"name": "Partes", "value": "Empresa A e B", "confidence": 0.95},
                {"name": "Valor", "value": "R$ 50.000", "confidence": 0.88},
                {"name": "Prazo", "value": "12 meses", "confidence": 0.92},
                {"name": "Assinaturas", "value": "João, Maria", "confidence": 0.80},
            ]
        }
        fields = _parse_extraction_response(response, "Contrato")

        assert len(fields) == 4
        assert {f.name for f in fields} == {"Partes", "Valor", "Prazo", "Assinaturas"}
        assert all(f.value is not None for f in fields)
        assert all(0.0 <= f.confidence <= 1.0 for f in fields)

    def test_nota_fiscal_all_fields_present(self) -> None:
        """Nota Fiscal with all 6 fields returned."""
        response = {
            "fields": [
                {"name": "Emitente", "value": "Tech Corp", "confidence": 0.97},
                {"name": "CNPJ", "value": "12.345.678/0001-90", "confidence": 0.99},
                {"name": "Número da Nota", "value": "NF-001234", "confidence": 0.95},
                {"name": "Itens", "value": "notebook, mouse", "confidence": 0.85},
                {"name": "Valor Total", "value": "R$ 8.500,00", "confidence": 0.93},
                {"name": "Data de Emissão", "value": "2024-01-15", "confidence": 0.98},
            ]
        }
        fields = _parse_extraction_response(response, "Nota Fiscal")

        assert len(fields) == 6
        assert {f.name for f in fields} == set(EXTRACTION_SCHEMAS["Nota Fiscal"])

    def test_generic_document_truncates_to_10(self) -> None:
        """Documento Genérico with 15 fields → truncated to 10 (Req 3.7)."""
        response = {
            "fields": [
                {"name": f"Campo {i}", "value": f"Valor {i}", "confidence": 0.8}
                for i in range(15)
            ]
        }
        fields = _parse_extraction_response(response, "Documento Genérico")

        assert len(fields) == 10
        assert fields[0].name == "Campo 0"
        assert fields[9].name == "Campo 9"

    def test_generic_document_fewer_than_10_not_truncated(self) -> None:
        response = {
            "fields": [
                {"name": f"Campo {i}", "value": f"Valor {i}", "confidence": 0.9}
                for i in range(5)
            ]
        }
        fields = _parse_extraction_response(response, "Documento Genérico")
        assert len(fields) == 5

    def test_missing_fields_filled_with_null_and_zero(self) -> None:
        """Missing schema fields get value=None, confidence=0.0 (Req 3.9)."""
        response = {
            "fields": [
                {"name": "Partes", "value": "Empresa A", "confidence": 0.95},
                {"name": "Valor", "value": "R$ 10.000", "confidence": 0.88},
            ]
        }
        fields = _parse_extraction_response(response, "Contrato")

        assert len(fields) == 4
        field_map = {f.name: f for f in fields}
        assert field_map["Prazo"].value is None
        assert field_map["Prazo"].confidence == 0.0
        assert field_map["Assinaturas"].value is None
        assert field_map["Assinaturas"].confidence == 0.0

    def test_null_value_forces_confidence_zero(self) -> None:
        """Invariant: null value → confidence = 0.0 (Req 3.9)."""
        response = {
            "fields": [
                {"name": "Partes", "value": None, "confidence": 0.85},
                {"name": "Valor", "value": "R$ 1.000", "confidence": 0.90},
                {"name": "Prazo", "value": None, "confidence": 0.7},
                {"name": "Assinaturas", "value": "João", "confidence": 0.6},
            ]
        }
        fields = _parse_extraction_response(response, "Contrato")
        field_map = {f.name: f for f in fields}

        assert field_map["Partes"].confidence == 0.0
        assert field_map["Prazo"].confidence == 0.0
        assert field_map["Valor"].confidence == 0.90
        assert field_map["Assinaturas"].confidence == 0.6

    def test_empty_fields_list_fills_schema(self) -> None:
        """Empty response fills all schema fields with null."""
        fields = _parse_extraction_response({"fields": []}, "Contrato")

        assert len(fields) == 4
        assert all(f.value is None and f.confidence == 0.0 for f in fields)

    def test_non_dict_entries_ignored(self) -> None:
        """Non-dict entries in fields array are skipped."""
        response = {
            "fields": [
                "invalid_string",
                42,
                {"name": "Partes", "value": "Empresa A", "confidence": 0.9},
            ]
        }
        fields = _parse_extraction_response(response, "Contrato")

        assert len(fields) == 4
        assert {f.name for f in fields} == {"Partes", "Valor", "Prazo", "Assinaturas"}

    def test_confidence_out_of_range_clamped(self) -> None:
        response = {
            "fields": [
                {"name": "Partes", "value": "Test", "confidence": 2.5},
                {"name": "Valor", "value": "Test", "confidence": -1.0},
                {"name": "Prazo", "value": "Test", "confidence": 0.5},
                {"name": "Assinaturas", "value": "Test", "confidence": "bad"},
            ]
        }
        fields = _parse_extraction_response(response, "Contrato")
        field_map = {f.name: f for f in fields}

        assert field_map["Partes"].confidence == 1.0
        assert field_map["Valor"].confidence == 0.0
        assert field_map["Prazo"].confidence == 0.5
        assert field_map["Assinaturas"].confidence == 0.0


# ---------------------------------------------------------------------------
# Tests for extract_fields (full integration with mocked deps)
# ---------------------------------------------------------------------------


class TestExtractFields:
    @patch("modules.extractor.put_item")
    @patch("modules.extractor.update_item")
    @patch("modules.extractor.invoke_claude_json")
    @patch("modules.extractor.download_file")
    @patch("modules.extractor.get_item")
    def test_successful_contrato_extraction(
        self, mock_get, mock_dl, mock_invoke, mock_update, mock_put
    ) -> None:
        """Successful Contrato extraction returns all 4 fields (Req 3.2)."""
        mock_get.return_value = {
            "document_id": "doc-1",
            "category": "Contrato",
            "s3_key": "documents/doc-1.pdf",
            "file_format": "pdf",
        }
        mock_dl.return_value = b"pdf-content"
        mock_invoke.return_value = {
            "fields": [
                {"name": "Partes", "value": "Empresa A e B", "confidence": 0.95},
                {"name": "Valor", "value": "R$ 100.000", "confidence": 0.90},
                {"name": "Prazo", "value": "24 meses", "confidence": 0.88},
                {"name": "Assinaturas", "value": "A. Silva, B. Santos", "confidence": 0.85},
            ]
        }

        result = extract_fields("doc-1")

        assert result.success is True
        assert result.document_id == "doc-1"
        assert len(result.fields) == 4
        assert all(f.value is not None for f in result.fields)
        mock_update.assert_called_once_with(
            "Documents", {"document_id": "doc-1"}, {"status": "extracted"}
        )
        mock_put.assert_called_once()

    @patch("modules.extractor.put_item")
    @patch("modules.extractor.update_item")
    @patch("modules.extractor.invoke_claude_json")
    @patch("modules.extractor.download_file")
    @patch("modules.extractor.get_item")
    def test_successful_nota_fiscal_extraction(
        self, mock_get, mock_dl, mock_invoke, mock_update, mock_put
    ) -> None:
        """Nota Fiscal extraction returns all 6 fields (Req 3.2)."""
        mock_get.return_value = {
            "document_id": "doc-2",
            "category": "Nota Fiscal",
            "s3_key": "documents/doc-2.pdf",
            "file_format": "pdf",
        }
        mock_dl.return_value = b"pdf-content"
        mock_invoke.return_value = {
            "fields": [
                {"name": "Emitente", "value": "Tech Corp", "confidence": 0.97},
                {"name": "CNPJ", "value": "12.345.678/0001-90", "confidence": 0.99},
                {"name": "Número da Nota", "value": "NF-5678", "confidence": 0.95},
                {"name": "Itens", "value": "Consultoria", "confidence": 0.88},
                {"name": "Valor Total", "value": "R$ 15.000", "confidence": 0.93},
                {"name": "Data de Emissão", "value": "2024-03-20", "confidence": 0.98},
            ]
        }

        result = extract_fields("doc-2")

        assert result.success is True
        assert len(result.fields) == 6
        assert {f.name for f in result.fields} == set(EXTRACTION_SCHEMAS["Nota Fiscal"])

    @patch("modules.extractor.put_item")
    @patch("modules.extractor.update_item")
    @patch("modules.extractor.invoke_claude_json")
    @patch("modules.extractor.download_file")
    @patch("modules.extractor.get_item")
    def test_generic_document_truncates_to_10(
        self, mock_get, mock_dl, mock_invoke, mock_update, mock_put
    ) -> None:
        """Generic document with >10 fields truncates to 10 (Req 3.7)."""
        mock_get.return_value = {
            "document_id": "doc-3",
            "category": "Documento Genérico",
            "s3_key": "documents/doc-3.png",
            "file_format": "png",
        }
        mock_dl.return_value = b"image-content"
        mock_invoke.return_value = {
            "fields": [
                {"name": f"Campo {i}", "value": f"Valor {i}", "confidence": 0.8}
                for i in range(15)
            ]
        }

        result = extract_fields("doc-3")

        assert result.success is True
        assert len(result.fields) == 10

    @patch("modules.extractor.get_item")
    def test_document_not_found_returns_error(self, mock_get) -> None:
        mock_get.return_value = None

        result = extract_fields("nonexistent-id")

        assert result.success is False
        assert result.document_id == "nonexistent-id"
        assert "não encontrado" in result.error_message

    @patch("modules.extractor.update_item")
    @patch("modules.extractor.download_file")
    @patch("modules.extractor.get_item")
    def test_s3_download_failure_sets_extraction_error(
        self, mock_get, mock_dl, mock_update
    ) -> None:
        """S3 download failure → extraction_error status."""
        mock_get.return_value = {
            "document_id": "doc-4",
            "category": "Contrato",
            "s3_key": "documents/doc-4.pdf",
            "file_format": "pdf",
        }
        mock_dl.return_value = b""

        result = extract_fields("doc-4")

        assert result.success is False
        assert "S3" in result.error_message
        mock_update.assert_called_once_with(
            "Documents", {"document_id": "doc-4"}, {"status": "extraction_error"}
        )

    @patch("modules.extractor.update_item")
    @patch("modules.extractor.invoke_claude_json")
    @patch("modules.extractor.download_file")
    @patch("modules.extractor.get_item")
    def test_bedrock_returns_none_sets_extraction_error(
        self, mock_get, mock_dl, mock_invoke, mock_update
    ) -> None:
        """Bedrock returning None (timeout) → extraction_error."""
        mock_get.return_value = {
            "document_id": "doc-5",
            "category": "Contrato",
            "s3_key": "documents/doc-5.pdf",
            "file_format": "pdf",
        }
        mock_dl.return_value = b"pdf-content"
        mock_invoke.return_value = None

        result = extract_fields("doc-5")

        assert result.success is False
        assert "Timeout" in result.error_message or "falha" in result.error_message
        mock_update.assert_called_once_with(
            "Documents", {"document_id": "doc-5"}, {"status": "extraction_error"}
        )

    @patch("modules.extractor.update_item")
    @patch("modules.extractor.invoke_claude_json")
    @patch("modules.extractor.download_file")
    @patch("modules.extractor.get_item")
    def test_bedrock_exception_sets_extraction_error(
        self, mock_get, mock_dl, mock_invoke, mock_update
    ) -> None:
        """Bedrock raising exception → extraction_error."""
        mock_get.return_value = {
            "document_id": "doc-6",
            "category": "Nota Fiscal",
            "s3_key": "documents/doc-6.jpg",
            "file_format": "jpg",
        }
        mock_dl.return_value = b"image-bytes"
        mock_invoke.side_effect = TimeoutError("Connection timed out")

        result = extract_fields("doc-6")

        assert result.success is False
        assert result.error_message is not None
        mock_update.assert_called_once_with(
            "Documents", {"document_id": "doc-6"}, {"status": "extraction_error"}
        )

    @patch("modules.extractor.put_item")
    @patch("modules.extractor.update_item")
    @patch("modules.extractor.invoke_claude_json")
    @patch("modules.extractor.download_file")
    @patch("modules.extractor.get_item")
    def test_null_values_always_get_zero_confidence(
        self, mock_get, mock_dl, mock_invoke, mock_update, mock_put
    ) -> None:
        """Null values always get confidence=0.0 (Req 3.9 invariant enforcement)."""
        mock_get.return_value = {
            "document_id": "doc-7",
            "category": "Contrato",
            "s3_key": "documents/doc-7.pdf",
            "file_format": "pdf",
        }
        mock_dl.return_value = b"pdf-content"
        mock_invoke.return_value = {
            "fields": [
                {"name": "Partes", "value": None, "confidence": 0.85},
                {"name": "Valor", "value": "R$ 5.000", "confidence": 0.90},
                {"name": "Prazo", "value": None, "confidence": 0.7},
                {"name": "Assinaturas", "value": "João", "confidence": 0.6},
            ]
        }

        result = extract_fields("doc-7")

        assert result.success is True
        field_map = {f.name: f for f in result.fields}
        # Null values → confidence forced to 0.0
        assert field_map["Partes"].confidence == 0.0
        assert field_map["Prazo"].confidence == 0.0
        # Non-null values keep original
        assert field_map["Valor"].confidence == 0.90
        assert field_map["Assinaturas"].confidence == 0.6


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis)
# ---------------------------------------------------------------------------

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st


# --- Strategies ---

SPECIFIC_CATEGORIES = [cat for cat in EXTRACTION_SCHEMAS if cat != "Documento Genérico"]

specific_categories = st.sampled_from(SPECIFIC_CATEGORIES)

field_values = st.one_of(st.none(), st.text(min_size=1, max_size=200))

raw_confidences = st.floats(min_value=-1.0, max_value=2.0, allow_nan=False, allow_infinity=False)

raw_field_dicts = st.fixed_dictionaries(
    {"name": st.text(min_size=1, max_size=50), "value": field_values, "confidence": raw_confidences}
)

generic_field_lists = st.lists(raw_field_dicts, min_size=0, max_size=20)


def _build_response_with_subset(category: str, draw) -> dict:
    """Build a Bedrock-style response with a random subset of schema fields."""
    schema_fields = EXTRACTION_SCHEMAS[category]
    included = draw(st.lists(st.sampled_from(schema_fields), min_size=0, max_size=len(schema_fields), unique=True))
    extra_fields = draw(st.lists(raw_field_dicts, min_size=0, max_size=3))

    fields = [
        {"name": name, "value": draw(field_values), "confidence": draw(raw_confidences)}
        for name in included
    ]
    fields.extend(extra_fields)
    return {"fields": fields}


# Feature: document-intelligence-copilot, Property 5: Extraction produces all schema-defined fields for the category


class TestExtractionSchemaCompleteness:
    """
    Property 5: Extraction produces all schema-defined fields for the category.

    **Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6**
    """

    @given(data=st.data(), category=specific_categories)
    @hyp_settings(max_examples=100)
    def test_all_schema_fields_present_in_output(self, data, category: str) -> None:
        """For specific categories, ALL schema fields must appear in the output."""
        response = _build_response_with_subset(category, data.draw)
        result = _parse_extraction_response(response, category)

        schema_fields = set(EXTRACTION_SCHEMAS[category])
        result_field_names = {f.name for f in result}

        assert schema_fields.issubset(result_field_names), (
            f"Missing fields for {category}: {schema_fields - result_field_names}"
        )

    @given(category=specific_categories)
    @hyp_settings(max_examples=100)
    def test_empty_response_fills_all_schema_fields(self, category: str) -> None:
        """Empty response still produces all schema fields with null/0.0."""
        result = _parse_extraction_response({"fields": []}, category)

        schema_fields = EXTRACTION_SCHEMAS[category]
        for field_name in schema_fields:
            matching = [f for f in result if f.name == field_name]
            assert len(matching) >= 1, f"Field {field_name} missing from output"
            assert matching[0].value is None
            assert matching[0].confidence == 0.0


# Feature: document-intelligence-copilot, Property 6: Generic document extraction respects maximum field count


class TestGenericExtractionMaxFields:
    """
    Property 6: Generic document extraction respects maximum field count.

    **Validates: Requirements 3.7**
    """

    @given(fields=generic_field_lists)
    @hyp_settings(max_examples=100)
    def test_generic_category_limited_to_10_fields(self, fields: list[dict]) -> None:
        """Documento Genérico output has at most 10 fields regardless of input size."""
        result = _parse_extraction_response({"fields": fields}, "Documento Genérico")

        assert len(result) <= 10, (
            f"Generic extraction returned {len(result)} fields (max 10 allowed)"
        )

    @given(fields=st.lists(raw_field_dicts, min_size=11, max_size=20))
    @hyp_settings(max_examples=100)
    def test_generic_truncates_when_over_10(self, fields: list[dict]) -> None:
        """When input has > 10 fields, output is truncated to exactly 10."""
        result = _parse_extraction_response({"fields": fields}, "Documento Genérico")

        assert len(result) == 10


# Feature: document-intelligence-copilot, Property 7: Null extraction values have zero confidence


class TestNullValueZeroConfidence:
    """
    Property 7: Null extraction values have zero confidence.

    **Validates: Requirements 3.9**
    """

    @given(data=st.data(), category=specific_categories)
    @hyp_settings(max_examples=100)
    def test_null_value_implies_zero_confidence_specific(self, data, category: str) -> None:
        """For specific categories, any field with value=None has confidence=0.0."""
        response = _build_response_with_subset(category, data.draw)
        result = _parse_extraction_response(response, category)

        for field in result:
            if field.value is None:
                assert field.confidence == 0.0, (
                    f"Field '{field.name}' has value=None but confidence={field.confidence}"
                )

    @given(fields=generic_field_lists)
    @hyp_settings(max_examples=100)
    def test_null_value_implies_zero_confidence_generic(self, fields: list[dict]) -> None:
        """For Documento Genérico, any field with value=None has confidence=0.0."""
        result = _parse_extraction_response({"fields": fields}, "Documento Genérico")

        for field in result:
            if field.value is None:
                assert field.confidence == 0.0, (
                    f"Field '{field.name}' has value=None but confidence={field.confidence}"
                )

    @given(
        name=st.text(min_size=1, max_size=30),
        confidence=st.floats(min_value=0.01, max_value=1.0, allow_nan=False),
    )
    @hyp_settings(max_examples=100)
    def test_null_value_with_nonzero_confidence_gets_corrected(
        self, name: str, confidence: float
    ) -> None:
        """Even if raw response has null value + high confidence, output enforces 0.0."""
        response = {"fields": [{"name": name, "value": None, "confidence": confidence}]}
        result = _parse_extraction_response(response, "Documento Genérico")

        for field in result:
            if field.value is None:
                assert field.confidence == 0.0
