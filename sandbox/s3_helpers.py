"""S3 helper functions for sandbox code execution.

This module provides convenient functions for reading and writing files to/from AWS S3.
It is automatically injected into each job directory, making it importable by executed code.
"""

import boto3
import os
import pandas as pd
from io import StringIO
from botocore.exceptions import ClientError
from botocore.config import Config


def get_default_bucket() -> str | None:
    """Get default bucket name from environment variable.
    
    Returns:
        Default bucket name if configured, None otherwise
    """
    bucket = os.getenv('AWS_DEFAULT_BUCKET')
    return bucket if bucket else None  # Normalize empty string to None


def get_allowed_buckets() -> list[str]:
    """Get list of allowed buckets from environment variable.
    
    Returns:
        List of allowed bucket names, empty list if not configured
    """
    allowed = os.getenv('ALLOWED_S3_BUCKETS', '')
    if allowed:
        return [bucket.strip() for bucket in allowed.split(',')]
    return []


def validate_bucket(bucket: str) -> None:
    """Validate that a bucket is allowed (if whitelist is configured).
    
    Args:
        bucket: Bucket name to validate
        
    Raises:
        ValueError: If bucket is not in the allowed list
    """
    allowed_buckets = get_allowed_buckets()
    if allowed_buckets and bucket not in allowed_buckets:
        raise ValueError(
            f"Bucket '{bucket}' is not in the allowed list. "
            f"Allowed buckets: {', '.join(allowed_buckets)}"
        )


def get_s3_client():
    """Get configured S3 client with credentials from environment.
    
    Returns:
        boto3 S3 client configured with AWS credentials
        
    Note:
        Configured with minimal max_pool_connections to avoid thread usage
        in resource-constrained sandbox environment.
    """
    # A self-hosted, S3-compatible server (MinIO, Ceph, LocalStack) is reached by
    # host:port and generally cannot serve virtual-host addressing, which would
    # resolve buckets as http://my-bucket.localhost:9000. Default to path style
    # whenever a custom endpoint is set. This mirrors
    # settings.s3_addressing_style_resolved in the backend; the sandbox is a
    # separate service and cannot import it.
    #
    # Both values are normalised first. python-dotenv strips `# comment` from a
    # value but Docker Compose's env_file parser does not necessarily, and
    # botocore raises InvalidS3AddressingStyleError for anything it does not
    # recognise — taking out every S3 call, not just this setting.
    endpoint_url = os.getenv('AWS_ENDPOINT_URL', '').split('#')[0].strip() or None

    addressing_style = os.getenv('AWS_S3_ADDRESSING_STYLE', '').split('#')[0].strip().lower()
    if addressing_style not in ('path', 'virtual'):
        addressing_style = 'path' if endpoint_url else 'auto'

    # Configure boto3 to use single connection for sandbox environment
    # This completely avoids threading issues with strict RLIMIT_NPROC
    config = Config(
        max_pool_connections=1,  # Single connection to avoid threading
        retries={'max_attempts': 3, 'mode': 'standard'},
        s3={'addressing_style': addressing_style}
    )
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        aws_session_token=os.getenv('AWS_SESSION_TOKEN'),  # Optional, for temporary credentials
        region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
        endpoint_url=endpoint_url,
        config=config
    )


def read_csv_from_s3(key: str, bucket: str | None = None) -> pd.DataFrame:
    """Read CSV file from S3 and return as pandas DataFrame.
    
    Args:
        key: S3 object key (file path)
        bucket: S3 bucket name (optional, uses AWS_DEFAULT_BUCKET if not provided)
        
    Returns:
        pandas DataFrame with CSV data
        
    Raises:
        Exception: If file cannot be read or parsed
    """
    # Use default bucket if not provided
    if bucket is None:
        bucket = get_default_bucket()
        if bucket is None:
            raise ValueError("Bucket name must be provided or AWS_DEFAULT_BUCKET must be set")
    
    # Validate bucket if whitelist is configured
    validate_bucket(bucket)
    
    try:
        s3 = get_s3_client()
        obj = s3.get_object(Bucket=bucket, Key=key)
        csv_content = obj['Body'].read().decode('utf-8')
        return pd.read_csv(StringIO(csv_content))
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'NoSuchKey':
            raise Exception(f"File not found: s3://{bucket}/{key}")
        elif error_code == 'AccessDenied':
            raise Exception(f"Access denied to: s3://{bucket}/{key}")
        else:
            raise Exception(f"Error reading from S3: {str(e)}")
    except Exception as e:
        raise Exception(f"Error reading CSV from S3: {str(e)}")


def read_file_from_s3(key: str, bucket: str | None = None) -> str:
    """Read text file from S3 and return as string.
    
    Args:
        key: S3 object key (file path)
        bucket: S3 bucket name (optional, uses AWS_DEFAULT_BUCKET if not provided)
        
    Returns:
        File content as string
        
    Raises:
        Exception: If file cannot be read
    """
    # Use default bucket if not provided
    if bucket is None:
        bucket = get_default_bucket()
        if bucket is None:
            raise ValueError("Bucket name must be provided or AWS_DEFAULT_BUCKET must be set")
    
    # Validate bucket if whitelist is configured
    validate_bucket(bucket)
    
    try:
        s3 = get_s3_client()
        obj = s3.get_object(Bucket=bucket, Key=key)
        return obj['Body'].read().decode('utf-8')
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'NoSuchKey':
            raise Exception(f"File not found: s3://{bucket}/{key}")
        elif error_code == 'AccessDenied':
            raise Exception(f"Access denied to: s3://{bucket}/{key}")
        else:
            raise Exception(f"Error reading from S3: {str(e)}")
    except Exception as e:
        raise Exception(f"Error reading file from S3: {str(e)}")


def write_csv_to_s3(df: pd.DataFrame, key: str, bucket: str | None = None, **kwargs):
    """Write pandas DataFrame to S3 as CSV.
    
    Args:
        df: pandas DataFrame to write
        key: S3 object key (file path)
        bucket: S3 bucket name (optional, uses AWS_DEFAULT_BUCKET if not provided)
        **kwargs: Additional arguments for pandas to_csv() method
        
    Raises:
        Exception: If file cannot be written
    """
    # Use default bucket if not provided
    if bucket is None:
        bucket = get_default_bucket()
        if bucket is None:
            raise ValueError("Bucket name must be provided or AWS_DEFAULT_BUCKET must be set")
    
    # Validate bucket if whitelist is configured
    validate_bucket(bucket)
    
    try:
        s3 = get_s3_client()
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, **kwargs)
        s3.put_object(Bucket=bucket, Key=key, Body=csv_buffer.getvalue().encode('utf-8'))
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'AccessDenied':
            raise Exception(f"Access denied writing to: s3://{bucket}/{key}")
        else:
            raise Exception(f"Error writing to S3: {str(e)}")
    except Exception as e:
        raise Exception(f"Error writing CSV to S3: {str(e)}")


def write_file_to_s3(content: str, key: str, bucket: str | None = None):
    """Write text content to S3.
    
    Args:
        content: File content as string
        key: S3 object key (file path)
        bucket: S3 bucket name (optional, uses AWS_DEFAULT_BUCKET if not provided)
        
    Raises:
        Exception: If file cannot be written
    """
    # Use default bucket if not provided
    if bucket is None:
        bucket = get_default_bucket()
        if bucket is None:
            raise ValueError("Bucket name must be provided or AWS_DEFAULT_BUCKET must be set")
    
    # Validate bucket if whitelist is configured
    validate_bucket(bucket)
    
    try:
        s3 = get_s3_client()
        s3.put_object(Bucket=bucket, Key=key, Body=content.encode('utf-8'))
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'AccessDenied':
            raise Exception(f"Access denied writing to: s3://{bucket}/{key}")
        else:
            raise Exception(f"Error writing to S3: {str(e)}")
    except Exception as e:
        raise Exception(f"Error writing file to S3: {str(e)}")


def upload_file_to_s3(local_path: str, key: str, bucket: str | None = None):
    """Upload a local file (e.g., plot image) to S3.
    
    Args:
        local_path: Path to local file
        key: S3 object key (file path)
        bucket: S3 bucket name (optional, uses AWS_DEFAULT_BUCKET if not provided)
        
    Raises:
        Exception: If file cannot be uploaded
    """
    # Use default bucket if not provided
    if bucket is None:
        bucket = get_default_bucket()
        if bucket is None:
            raise ValueError("Bucket name must be provided or AWS_DEFAULT_BUCKET must be set")
    
    # Validate bucket if whitelist is configured
    validate_bucket(bucket)
    
    try:
        s3 = get_s3_client()
        # For smaller files (< 5MB), use put_object to avoid threading issues
        # For larger files, upload_file uses multipart upload with threads
        import os
        file_size = os.path.getsize(local_path)
        
        if file_size < 5 * 1024 * 1024:  # 5MB threshold
            # Use put_object for small files (no threading)
            print(f"[S3] Uploading {local_path} ({file_size} bytes) using put_object (single thread)", flush=True)
            with open(local_path, 'rb') as f:
                s3.put_object(Bucket=bucket, Key=key, Body=f.read())
            print(f"[S3] ✓ Upload successful: s3://{bucket}/{key}", flush=True)
        else:
            # Use upload_file for larger files (uses multipart upload)
            print(f"[S3] Uploading {local_path} ({file_size} bytes) using multipart upload", flush=True)
            s3.upload_file(local_path, bucket, key)
            print(f"[S3] ✓ Upload successful: s3://{bucket}/{key}", flush=True)
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        error_msg = f"ClientError {error_code}: {str(e)}"
        print(f"[S3] ✗ Upload failed: {error_msg}", flush=True)
        if error_code == 'AccessDenied':
            raise Exception(f"Access denied uploading to: s3://{bucket}/{key}")
        else:
            raise Exception(f"Error uploading to S3: {str(e)}")
    except FileNotFoundError:
        error_msg = f"Local file not found: {local_path}"
        print(f"[S3] ✗ Upload failed: {error_msg}", flush=True)
        raise Exception(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
        print(f"[S3] ✗ Upload failed: {error_msg}", flush=True)
        raise Exception(f"Error uploading file to S3: {str(e)}")


def list_s3_files(prefix: str = "", bucket: str | None = None) -> list[str]:
    """List files in S3 bucket with optional prefix filter.
    
    Args:
        prefix: Optional prefix to filter files (e.g., 'data/raw/')
        bucket: S3 bucket name (optional, uses AWS_DEFAULT_BUCKET if not provided)
        
    Returns:
        List of S3 object keys matching the prefix
        
    Raises:
        Exception: If bucket cannot be accessed
    """
    # Use default bucket if not provided
    if bucket is None:
        bucket = get_default_bucket()
        if bucket is None:
            raise ValueError("Bucket name must be provided or AWS_DEFAULT_BUCKET must be set")
    
    # Validate bucket if whitelist is configured
    validate_bucket(bucket)
    
    try:
        s3 = get_s3_client()
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        return [obj['Key'] for obj in response.get('Contents', [])]
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'AccessDenied':
            raise Exception(f"Access denied to bucket: {bucket}")
        else:
            raise Exception(f"Error listing S3 files: {str(e)}")
    except Exception as e:
        raise Exception(f"Error listing files in S3: {str(e)}")

