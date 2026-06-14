"""Bedrock client wrapper for Claude model invocations."""

import json
import base64
import time
import logging
from functools import wraps
from typing import Callable, TypeVar

import boto3
from botocore.exceptions import ClientError, ReadTimeoutError

from config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(max_attempts: int = 2, backoff_base: float = 2.0):
    """Retry com backoff exponencial. Retorna None se todas tentativas falharem."""

    def decorator(func: Callable[..., T]) -> Callable[..., T | None]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T | None:
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (TimeoutError, ConnectionError, ReadTimeoutError):
                    logger.warning(
                        "Attempt %d/%d failed for %s",
                        attempt + 1,
                        max_attempts,
                        func.__name__,
                    )
                    if attempt < max_attempts - 1:
                        time.sleep(backoff_base**attempt)
            return None

        return wrapper

    return decorator


def get_bedrock_client():
    """Create and return a Bedrock Runtime client."""
    settings = get_settings()
    return boto3.client("bedrock-runtime", region_name=settings.aws_region)


def _build_file_block(file_bytes: bytes, media_type: str) -> dict:
    """Build the appropriate content block for a file attachment."""
    encoded = base64.standard_b64encode(file_bytes).decode("utf-8")

    if media_type == "application/pdf":
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": encoded,
            },
        }

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": encoded,
        },
    }


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from Claude's response if present."""
    stripped = text.strip()
    if stripped.startswith("```json"):
        stripped = stripped[7:]
    elif stripped.startswith("```"):
        stripped = stripped[3:]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    return stripped.strip()


@with_retry(max_attempts=2, backoff_base=2.0)
def invoke_claude_json(
    prompt: str,
    system: str = "",
    file_bytes: bytes | None = None,
    media_type: str | None = None,
    max_tokens: int = 4096,
) -> dict:
    """Invoca Claude e parseia resposta como JSON. Suporta texto puro ou multimodal."""
    settings = get_settings()
    client = get_bedrock_client()

    content: list[dict] = []
    if file_bytes is not None and media_type is not None:
        content.append(_build_file_block(file_bytes, media_type))
    content.append({"type": "text", "text": prompt})

    body: dict = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        body["system"] = system

    try:
        response = client.invoke_model(
            modelId=settings.bedrock_model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("ThrottlingException", "ServiceUnavailableException"):
            raise ConnectionError(f"Bedrock service unavailable: {error_code}") from e
        if "timeout" in str(e).lower():
            raise TimeoutError(f"Bedrock request timed out: {e}") from e
        raise
    except ReadTimeoutError as e:
        raise TimeoutError(f"Bedrock read timeout: {e}") from e

    response_body = json.loads(response["body"].read())

    # Extract first text block from response
    response_text = next(
        (block["text"] for block in response_body.get("content", []) if block.get("type") == "text"),
        "",
    )

    cleaned = _strip_markdown_fences(response_text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse Claude response as JSON: {e}") from e
