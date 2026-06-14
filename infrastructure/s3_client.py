"""S3 client wrapper for document storage operations."""

import logging

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

from config import get_settings

logger = logging.getLogger(__name__)


def _get_s3_client():
    """Create and return a boto3 S3 client configured with the app region."""
    settings = get_settings()
    return boto3.client("s3", region_name=settings.aws_region)


def upload_file(file_bytes: bytes, key: str, content_type: str) -> bool:
    """Upload file bytes to S3.

    Returns True if upload succeeded, False on any connection or client error.
    """
    settings = get_settings()
    try:
        client = _get_s3_client()
        client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
            Body=file_bytes,
            ContentType=content_type,
        )
        return True
    except (ClientError, EndpointConnectionError, ConnectionError) as exc:
        logger.error("S3 upload failed for key=%s: %s", key, exc)
        return False


def download_file(key: str) -> bytes:
    """Download file content from S3.

    Returns file content as bytes, or empty bytes on error.
    """
    settings = get_settings()
    try:
        client = _get_s3_client()
        response = client.get_object(Bucket=settings.s3_bucket_name, Key=key)
        return response["Body"].read()
    except (ClientError, EndpointConnectionError, ConnectionError) as exc:
        logger.error("S3 download failed for key=%s: %s", key, exc)
        return b""


def generate_presigned_url(key: str, expiry: int | None = None) -> str:
    """Generate a presigned URL for temporary access to an S3 object.

    Returns presigned URL string, or empty string on error.
    """
    settings = get_settings()
    if expiry is None:
        expiry = settings.s3_presigned_url_expiry
    try:
        client = _get_s3_client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_name, "Key": key},
            ExpiresIn=expiry,
        )
    except (ClientError, EndpointConnectionError, ConnectionError) as exc:
        logger.error("S3 presigned URL generation failed for key=%s: %s", key, exc)
        return ""
