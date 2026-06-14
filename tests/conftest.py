"""Shared test fixtures for Doc Intel Copilot tests."""

import os
import pytest

# Set environment variables before importing config to avoid validation errors
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    """Reset the lru_cache on get_settings between tests."""
    from config import get_settings
    get_settings.cache_clear()
