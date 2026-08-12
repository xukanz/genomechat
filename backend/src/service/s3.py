"""S3 client service for backend operations."""

import logging
import threading
from typing import Optional

import boto3
from botocore.config import Config

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Module-level singleton for S3 client
_s3_client: Optional[boto3.client] = None
_s3_client_lock = threading.Lock()


def get_s3_client():
    """Get configured S3 client singleton with credentials from environment or IAM role.

    Uses thread-safe singleton pattern to reuse the same client across requests.
    boto3 clients are thread-safe and handle connection pooling internally.

    If AWS credentials are provided, uses them explicitly.
    Otherwise, uses boto3 default credential chain (IAM roles, instance profiles, etc.).

    Credential resolution order (when not explicitly provided):
    1. IAM Task Role (ECS)
    2. Instance Profile (EC2)
    3. Environment variables
    4. ~/.aws/credentials

    Returns:
        boto3 S3 client configured with AWS credentials
    """
    global _s3_client

    if _s3_client is not None:
        return _s3_client

    with _s3_client_lock:
        # Double-check locking pattern
        if _s3_client is not None:
            return _s3_client

        kwargs = {
            "region_name": settings.aws_default_region,
            "config": Config(
                s3={"addressing_style": settings.s3_addressing_style_resolved},
            ),
        }

        # Point at a self-hosted, S3-compatible server when one is configured
        # (MinIO, Ceph, LocalStack). Unset means real AWS.
        if settings.aws_endpoint_url:
            kwargs["endpoint_url"] = settings.aws_endpoint_url
            logger.info(
                f"S3 client targeting custom endpoint {settings.aws_endpoint_url} "
                f"(addressing style: {settings.s3_addressing_style_resolved})"
            )

        # Only add explicit credentials if provided (for local dev or explicit credential scenarios)
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
            if settings.aws_session_token:
                kwargs["aws_session_token"] = settings.aws_session_token
            logger.info("S3 client initialized with explicit AWS credentials")
        else:
            logger.info(
                "S3 client initialized with default credential chain "
                "(IAM roles, instance profiles, etc.)"
            )

        _s3_client = boto3.client("s3", **kwargs)
        return _s3_client


def generate_presigned_url(bucket: str, key: str, expiration: int = 3600) -> str:
    """Generate presigned URL for S3 file access.

    Args:
        bucket: S3 bucket name
        key: S3 object key
        expiration: URL expiration time in seconds (default: 1 hour)

    Returns:
        Presigned URL string for GET access to the S3 object
    """
    s3_client = get_s3_client()
    url = s3_client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expiration
    )
    logger.info(f"Generated presigned URL for s3://{bucket}/{key} (expires in {expiration}s)")
    return url
