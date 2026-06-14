"""Unit tests for infrastructure/bedrock_client.py."""

import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from infrastructure.bedrock_client import (
    _build_file_block,
    _strip_markdown_fences,
    invoke_claude_json,
    with_retry,
)


# --- with_retry decorator ---


def test_retry_returns_on_first_success():
    @with_retry(max_attempts=3)
    def success():
        return {"key": "value"}

    assert success() == {"key": "value"}


def test_retry_recovers_from_timeout():
    call_count = 0

    @with_retry(max_attempts=3, backoff_base=0.01)
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("timed out")
        return {"ok": True}

    assert flaky() == {"ok": True}
    assert call_count == 3


def test_retry_recovers_from_connection_error():
    call_count = 0

    @with_retry(max_attempts=2, backoff_base=0.01)
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("network issue")
        return {"ok": True}

    assert flaky() == {"ok": True}


def test_retry_returns_none_when_exhausted():
    @with_retry(max_attempts=2, backoff_base=0.01)
    def always_fails():
        raise TimeoutError("always times out")

    assert always_fails() is None


def test_retry_does_not_catch_unrelated_exceptions():
    @with_retry(max_attempts=3, backoff_base=0.01)
    def raises_value_error():
        raise ValueError("not transient")

    with pytest.raises(ValueError, match="not transient"):
        raises_value_error()


def test_retry_applies_exponential_backoff():
    @with_retry(max_attempts=3, backoff_base=2.0)
    def always_timeout():
        raise TimeoutError("timeout")

    with patch("infrastructure.bedrock_client.time.sleep") as mock_sleep:
        always_timeout()

    mock_sleep.assert_any_call(1.0)  # 2^0
    mock_sleep.assert_any_call(2.0)  # 2^1


# --- Helper functions ---


def test_build_file_block_pdf():
    block = _build_file_block(b"pdf data", "application/pdf")
    assert block["document"]["format"] == "pdf"
    assert "bytes" in block["document"]["source"]


def test_build_file_block_png():
    block = _build_file_block(b"png data", "image/png")
    assert block["image"]["format"] == "png"


def test_build_file_block_jpeg():
    block = _build_file_block(b"jpeg data", "image/jpeg")
    assert block["image"]["format"] == "jpeg"


def test_strip_markdown_fences_plain_json():
    assert _strip_markdown_fences('{"k": "v"}') == '{"k": "v"}'


def test_strip_markdown_fences_json_block():
    assert _strip_markdown_fences('```json\n{"k": "v"}\n```') == '{"k": "v"}'


def test_strip_markdown_fences_generic_block():
    assert _strip_markdown_fences('```\n{"k": "v"}\n```') == '{"k": "v"}'


# --- invoke_claude_json ---


def _mock_response(json_body: dict) -> dict:
    """Create a mock Bedrock response."""
    payload = {"content": [{"type": "text", "text": json.dumps(json_body)}]}
    body = MagicMock()
    body.read.return_value = json.dumps(payload).encode()
    return {"body": body}


@patch("infrastructure.bedrock_client.get_bedrock_client")
def test_invoke_text_only(mock_get_client):
    expected = {"category": "Contrato", "confidence": 0.95}
    client = MagicMock()
    client.invoke_model.return_value = _mock_response(expected)
    mock_get_client.return_value = client

    result = invoke_claude_json(prompt="Classify this", system="You are a classifier")

    assert result == expected
    body = json.loads(client.invoke_model.call_args.kwargs["body"])
    assert body["system"] == "You are a classifier"
    assert body["messages"][0]["content"] == [{"text": "Classify this"}]


@patch("infrastructure.bedrock_client.get_bedrock_client")
def test_invoke_multimodal_pdf(mock_get_client):
    expected = {"fields": [{"name": "Valor", "value": "R$ 1000"}]}
    client = MagicMock()
    client.invoke_model.return_value = _mock_response(expected)
    mock_get_client.return_value = client

    result = invoke_claude_json(
        prompt="Extract fields",
        file_bytes=b"pdf content",
        media_type="application/pdf",
    )

    assert result == expected
    body = json.loads(client.invoke_model.call_args.kwargs["body"])
    blocks = body["messages"][0]["content"]
    assert len(blocks) == 2
    assert "document" in blocks[0]
    assert blocks[1] == {"text": "Extract fields"}


@patch("infrastructure.bedrock_client.get_bedrock_client")
def test_invoke_multimodal_image(mock_get_client):
    expected = {"category": "Nota Fiscal"}
    client = MagicMock()
    client.invoke_model.return_value = _mock_response(expected)
    mock_get_client.return_value = client

    result = invoke_claude_json(prompt="Classify", file_bytes=b"img", media_type="image/png")

    assert result == expected
    body = json.loads(client.invoke_model.call_args.kwargs["body"])
    assert "image" in body["messages"][0]["content"][0]


@patch("infrastructure.bedrock_client.get_bedrock_client")
def test_invoke_handles_markdown_wrapped_json(mock_get_client):
    payload = {"content": [{"type": "text", "text": '```json\n{"result": true}\n```'}]}
    body_mock = MagicMock()
    body_mock.read.return_value = json.dumps(payload).encode()
    client = MagicMock()
    client.invoke_model.return_value = {"body": body_mock}
    mock_get_client.return_value = client

    assert invoke_claude_json(prompt="test") == {"result": True}


@patch("infrastructure.bedrock_client.get_bedrock_client")
def test_invoke_raises_on_invalid_json_response(mock_get_client):
    payload = {"content": [{"type": "text", "text": "Not JSON at all"}]}
    body_mock = MagicMock()
    body_mock.read.return_value = json.dumps(payload).encode()
    client = MagicMock()
    client.invoke_model.return_value = {"body": body_mock}
    mock_get_client.return_value = client

    with pytest.raises(ValueError, match="Failed to parse Claude response"):
        invoke_claude_json(prompt="test")


@patch("infrastructure.bedrock_client.time.sleep")
@patch("infrastructure.bedrock_client.get_bedrock_client")
def test_invoke_retries_on_throttling(mock_get_client, mock_sleep):
    expected = {"ok": True}
    client = MagicMock()
    error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "InvokeModel",
    )
    client.invoke_model.side_effect = [error, _mock_response(expected)]
    mock_get_client.return_value = client

    result = invoke_claude_json(prompt="test")

    assert result == expected
    assert client.invoke_model.call_count == 2


@patch("infrastructure.bedrock_client.time.sleep")
@patch("infrastructure.bedrock_client.get_bedrock_client")
def test_invoke_returns_none_after_all_retries_fail(mock_get_client, mock_sleep):
    client = MagicMock()
    error = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "InvokeModel",
    )
    client.invoke_model.side_effect = error
    mock_get_client.return_value = client

    assert invoke_claude_json(prompt="test") is None


@patch("infrastructure.bedrock_client.get_bedrock_client")
def test_invoke_omits_system_when_empty(mock_get_client):
    client = MagicMock()
    client.invoke_model.return_value = _mock_response({"x": 1})
    mock_get_client.return_value = client

    invoke_claude_json(prompt="test", system="")

    body = json.loads(client.invoke_model.call_args.kwargs["body"])
    assert "system" not in body
