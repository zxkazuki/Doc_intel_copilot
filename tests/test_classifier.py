"""Unit tests for modules/classifier.py — document classification logic."""

from unittest.mock import patch

import pytest

from modules.classifier import (
    DocumentCategory,
    ClassificationResult,
    classify_document,
    _parse_classification_response,
    _apply_confidence_fallback,
    _resolve_media_type,
    CONFIDENCE_THRESHOLD,
)


class TestResolveMediaType:
    """Tests for media type resolution."""

    @pytest.mark.parametrize(
        "file_format,expected",
        [
            ("pdf", "application/pdf"),
            ("png", "image/png"),
            ("jpg", "image/jpeg"),
            ("jpeg", "image/jpeg"),
            ("PDF", "application/pdf"),
            ("JPG", "image/jpeg"),
        ],
    )
    def test_known_formats(self, file_format: str, expected: str) -> None:
        assert _resolve_media_type(file_format) == expected

    def test_unknown_format_returns_octet_stream(self) -> None:
        assert _resolve_media_type("doc") == "application/octet-stream"


class TestParseClassificationResponse:
    """Tests for response parsing and validation."""

    def test_valid_response(self) -> None:
        response = {"category": "Contrato", "confidence": 0.95}
        result = _parse_classification_response(response)
        assert result is not None
        assert result.category == DocumentCategory.CONTRATO
        assert result.confidence == 0.95
        assert result.success is True

    def test_none_response(self) -> None:
        assert _parse_classification_response(None) is None

    def test_missing_category(self) -> None:
        assert _parse_classification_response({"confidence": 0.9}) is None

    def test_missing_confidence(self) -> None:
        assert _parse_classification_response({"category": "Contrato"}) is None

    def test_invalid_category(self) -> None:
        assert _parse_classification_response({"category": "Invalid", "confidence": 0.9}) is None

    def test_invalid_confidence_type(self) -> None:
        assert _parse_classification_response({"category": "Contrato", "confidence": "abc"}) is None

    def test_confidence_clamped_above_one(self) -> None:
        result = _parse_classification_response({"category": "Contrato", "confidence": 1.5})
        assert result.confidence == 1.0

    def test_confidence_clamped_below_zero(self) -> None:
        result = _parse_classification_response({"category": "Contrato", "confidence": -0.5})
        assert result.confidence == 0.0

    @pytest.mark.parametrize("category", list(DocumentCategory))
    def test_all_valid_categories(self, category: DocumentCategory) -> None:
        result = _parse_classification_response({"category": str(category), "confidence": 0.8})
        assert result is not None
        assert result.category == category


class TestApplyConfidenceFallback:
    """Tests for confidence threshold fallback logic."""

    def test_high_confidence_no_fallback(self) -> None:
        result = ClassificationResult(category=DocumentCategory.CONTRATO, confidence=0.9, success=True)
        assert _apply_confidence_fallback(result).category == DocumentCategory.CONTRATO

    def test_low_confidence_triggers_fallback(self) -> None:
        result = ClassificationResult(category=DocumentCategory.CONTRATO, confidence=0.5, success=True)
        applied = _apply_confidence_fallback(result)
        assert applied.category == DocumentCategory.DOCUMENTO_GENERICO
        assert applied.confidence == 0.5

    def test_exactly_at_threshold_no_fallback(self) -> None:
        result = ClassificationResult(category=DocumentCategory.NOTA_FISCAL, confidence=CONFIDENCE_THRESHOLD, success=True)
        assert _apply_confidence_fallback(result).category == DocumentCategory.NOTA_FISCAL

    def test_just_below_threshold_falls_back(self) -> None:
        result = ClassificationResult(category=DocumentCategory.LAUDO_MEDICO, confidence=0.69, success=True)
        assert _apply_confidence_fallback(result).category == DocumentCategory.DOCUMENTO_GENERICO

    def test_documento_generico_never_changed(self) -> None:
        result = ClassificationResult(category=DocumentCategory.DOCUMENTO_GENERICO, confidence=0.3, success=True)
        assert _apply_confidence_fallback(result).category == DocumentCategory.DOCUMENTO_GENERICO


class TestClassifyDocument:
    """Integration-style tests for classify_document with mocked dependencies."""

    @patch("modules.classifier.update_item")
    @patch("modules.classifier.invoke_claude_json")
    @patch("modules.classifier.download_file")
    @patch("modules.classifier.get_item")
    def test_successful_classification(self, mock_get, mock_dl, mock_invoke, mock_update) -> None:
        mock_get.return_value = {"document_id": "doc-1", "s3_key": "docs/doc-1.pdf", "file_format": "pdf"}
        mock_dl.return_value = b"pdf-bytes"
        mock_invoke.return_value = {"category": "Contrato", "confidence": 0.92}

        result = classify_document("doc-1")

        assert result.success is True
        assert result.category == DocumentCategory.CONTRATO
        assert result.confidence == 0.92
        mock_update.assert_called_once_with(
            "Documents",
            {"document_id": "doc-1"},
            {"category": "Contrato", "classification_confidence": "0.92", "status": "classified"},
        )

    @patch("modules.classifier.update_item")
    @patch("modules.classifier.invoke_claude_json")
    @patch("modules.classifier.download_file")
    @patch("modules.classifier.get_item")
    def test_low_confidence_triggers_fallback(self, mock_get, mock_dl, mock_invoke, mock_update) -> None:
        mock_get.return_value = {"document_id": "doc-2", "s3_key": "docs/doc-2.png", "file_format": "png"}
        mock_dl.return_value = b"image-bytes"
        mock_invoke.return_value = {"category": "Nota Fiscal", "confidence": 0.55}

        result = classify_document("doc-2")

        assert result.success is True
        assert result.category == DocumentCategory.DOCUMENTO_GENERICO
        assert result.confidence == 0.55

    @patch("modules.classifier.get_item")
    def test_document_not_found(self, mock_get) -> None:
        mock_get.return_value = None
        result = classify_document("nonexistent")
        assert result.success is False
        assert "não encontrado" in result.error_message

    @patch("modules.classifier.update_item")
    @patch("modules.classifier.download_file")
    @patch("modules.classifier.get_item")
    def test_s3_download_failure(self, mock_get, mock_dl, mock_update) -> None:
        mock_get.return_value = {"document_id": "doc-3", "s3_key": "docs/doc-3.pdf", "file_format": "pdf"}
        mock_dl.return_value = b""

        result = classify_document("doc-3")

        assert result.success is False
        assert "S3" in result.error_message
        mock_update.assert_called_once_with("Documents", {"document_id": "doc-3"}, {"status": "classification_error"})

    @patch("modules.classifier.update_item")
    @patch("modules.classifier.invoke_claude_json")
    @patch("modules.classifier.download_file")
    @patch("modules.classifier.get_item")
    def test_bedrock_exception_sets_error_status(self, mock_get, mock_dl, mock_invoke, mock_update) -> None:
        mock_get.return_value = {"document_id": "doc-4", "s3_key": "docs/doc-4.jpg", "file_format": "jpg"}
        mock_dl.return_value = b"image"
        mock_invoke.side_effect = TimeoutError("timeout")

        result = classify_document("doc-4")

        assert result.success is False
        assert "Bedrock" in result.error_message
        mock_update.assert_called_once_with("Documents", {"document_id": "doc-4"}, {"status": "classification_error"})

    @patch("modules.classifier.update_item")
    @patch("modules.classifier.invoke_claude_json")
    @patch("modules.classifier.download_file")
    @patch("modules.classifier.get_item")
    def test_bedrock_returns_none(self, mock_get, mock_dl, mock_invoke, mock_update) -> None:
        mock_get.return_value = {"document_id": "doc-5", "s3_key": "docs/doc-5.pdf", "file_format": "pdf"}
        mock_dl.return_value = b"pdf"
        mock_invoke.return_value = None

        result = classify_document("doc-5")

        assert result.success is False
        assert "inválida" in result.error_message
        mock_update.assert_called_once_with("Documents", {"document_id": "doc-5"}, {"status": "classification_error"})

    @patch("modules.classifier.update_item")
    @patch("modules.classifier.invoke_claude_json")
    @patch("modules.classifier.download_file")
    @patch("modules.classifier.get_item")
    def test_invalid_response_structure(self, mock_get, mock_dl, mock_invoke, mock_update) -> None:
        mock_get.return_value = {"document_id": "doc-6", "s3_key": "docs/doc-6.pdf", "file_format": "pdf"}
        mock_dl.return_value = b"pdf"
        mock_invoke.return_value = {"unexpected": "format"}

        result = classify_document("doc-6")

        assert result.success is False
        mock_update.assert_called_once_with("Documents", {"document_id": "doc-6"}, {"status": "classification_error"})


# =============================================================================
# Property-Based Tests (Hypothesis)
# =============================================================================

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# Feature: document-intelligence-copilot, Property 2: Classification output is always a valid category
class TestProperty2ClassificationOutputValidCategory:
    """
    Property 2: Classification output is always a valid category.

    For any classification result produced by _parse_classification_response,
    the category field SHALL be a valid member of the DocumentCategory enum.

    **Validates: Requirements 2.2**
    """

    @given(
        category=st.sampled_from(list(DocumentCategory)),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_parsed_result_always_has_valid_category(self, category: DocumentCategory, confidence: float) -> None:
        """Any valid response parsed by _parse_classification_response produces a valid DocumentCategory."""
        response = {"category": str(category), "confidence": confidence}
        result = _parse_classification_response(response)

        assert result is not None
        assert result.category in DocumentCategory
        assert isinstance(result.category, DocumentCategory)

    @given(
        category=st.sampled_from(list(DocumentCategory)),
        confidence=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_clamped_confidence_still_yields_valid_category(self, category: DocumentCategory, confidence: float) -> None:
        """Even with out-of-range confidence values, if the category is valid, result category is valid."""
        response = {"category": str(category), "confidence": confidence}
        result = _parse_classification_response(response)

        assert result is not None
        assert result.category in DocumentCategory


# Feature: document-intelligence-copilot, Property 3: Confidence scores are always in valid range
class TestProperty3ConfidenceScoresValidRange:
    """
    Property 3: Confidence scores are always in valid range.

    For any confidence score from classification (ClassificationResult.confidence),
    the value SHALL be a number in the range [0.0, 1.0].

    **Validates: Requirements 2.3**
    """

    @given(
        category=st.sampled_from(list(DocumentCategory)),
        confidence=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_confidence_always_clamped_to_valid_range(self, category: DocumentCategory, confidence: float) -> None:
        """For any numeric confidence input, _parse_classification_response clamps to [0.0, 1.0]."""
        response = {"category": str(category), "confidence": confidence}
        result = _parse_classification_response(response)

        assert result is not None
        assert 0.0 <= result.confidence <= 1.0

    @given(
        category=st.sampled_from(list(DocumentCategory)),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_valid_confidence_preserved_exactly(self, category: DocumentCategory, confidence: float) -> None:
        """Confidence values already in [0.0, 1.0] are preserved unchanged."""
        response = {"category": str(category), "confidence": confidence}
        result = _parse_classification_response(response)

        assert result is not None
        assert result.confidence == confidence


# Feature: document-intelligence-copilot, Property 4: Low confidence fallback to Documento Genérico
class TestProperty4LowConfidenceFallback:
    """
    Property 4: Low confidence fallback to Documento Genérico.

    For any result with confidence < 0.7 on a specific category (not Documento Genérico),
    _apply_confidence_fallback SHALL return Documento Genérico.

    **Validates: Requirements 2.4**
    """

    @given(
        category=st.sampled_from([c for c in DocumentCategory if c != DocumentCategory.DOCUMENTO_GENERICO]),
        confidence=st.floats(min_value=0.0, max_value=0.6999999, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_low_confidence_specific_category_falls_back_to_generico(
        self, category: DocumentCategory, confidence: float
    ) -> None:
        """Any specific category with confidence < 0.7 must fall back to Documento Genérico."""
        result = ClassificationResult(category=category, confidence=confidence, success=True)
        applied = _apply_confidence_fallback(result)

        assert applied.category == DocumentCategory.DOCUMENTO_GENERICO
        assert applied.confidence == confidence
        assert applied.success is True

    @given(
        category=st.sampled_from([c for c in DocumentCategory if c != DocumentCategory.DOCUMENTO_GENERICO]),
        confidence=st.floats(min_value=0.7, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_high_confidence_specific_category_no_fallback(
        self, category: DocumentCategory, confidence: float
    ) -> None:
        """Any specific category with confidence >= 0.7 keeps its original category."""
        result = ClassificationResult(category=category, confidence=confidence, success=True)
        applied = _apply_confidence_fallback(result)

        assert applied.category == category
        assert applied.confidence == confidence

    @given(
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_documento_generico_never_changes_regardless_of_confidence(self, confidence: float) -> None:
        """Documento Genérico is never changed by the fallback, even with low confidence."""
        result = ClassificationResult(
            category=DocumentCategory.DOCUMENTO_GENERICO, confidence=confidence, success=True
        )
        applied = _apply_confidence_fallback(result)

        assert applied.category == DocumentCategory.DOCUMENTO_GENERICO
