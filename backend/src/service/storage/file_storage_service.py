"""Unified file storage service for tracking all S3 files in MongoDB.

Tracks SQL query results, coder outputs, analyses, and any other files created by the system
in a single MongoDB collection with consistent metadata structure.
"""

import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from src.models.file_storage import FileRecord, FileRecordCreate, FileType, ArtifactResponse
from src.service.database.connections.mongodb_connection import get_mongodb_database
from src.service.s3 import get_s3_client
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Module-level flags for one-time initialization
_indexes_created = False
_indexes_lock = threading.Lock()

# Module-level cache for presigned URLs: {file_id: (url, expiry_timestamp)}
_url_cache: dict[str, tuple[str, float]] = {}
_url_cache_lock = threading.Lock()
# Cache URLs for 50 minutes (when they expire in 60 minutes) to allow buffer
URL_CACHE_BUFFER_SECONDS = 600  # 10 minutes buffer before expiry


class FileStorageService:
    """Unified service for tracking all S3 files in MongoDB."""

    def __init__(self, db_name: Optional[str] = None):
        """Initialize FileStorageService with MongoDB database.

        Args:
            db_name: MongoDB database name (defaults to settings.mongodb_db_name)
        """
        if db_name is None:
            db_name = getattr(settings, "mongodb_db_name", "langgraph_checkpoints")
        self.db = get_mongodb_database(db_name)
        self.files_collection = self.db["files"]
        self.conversations_collection = self.db["conversations"]
        self.s3_client = get_s3_client()
        self._ensure_indexes_once()

    def _ensure_indexes_once(self) -> None:
        """Create indexes on files collection (only once per application lifecycle).

        Uses module-level flag with thread-safe locking to ensure indexes
        are created only once, avoiding redundant MongoDB calls.
        """
        global _indexes_created

        if _indexes_created:
            return

        with _indexes_lock:
            # Double-check locking pattern
            if _indexes_created:
                return

            try:
                # Create unique index on file_id
                self.files_collection.create_index("file_id", unique=True)
                # Create compound index on user_id and created_at
                self.files_collection.create_index([("user_id", 1), ("created_at", -1)])
                # Create compound index on thread_id and created_at
                self.files_collection.create_index([("thread_id", 1), ("created_at", -1)])
                # Create compound index on file_type and created_at
                self.files_collection.create_index([("file_type", 1), ("created_at", -1)])
                # Create index on s3_key for lookups
                self.files_collection.create_index("s3_key")
                logger.info("Files collection indexes created/verified (one-time init)")
                _indexes_created = True
            except Exception as e:
                logger.warning(f"Failed to create files collection indexes: {e}")

    def save_file(
        self,
        file_data: FileRecordCreate,
        content: bytes,
    ) -> FileRecord:
        """Save file to S3 and metadata to MongoDB.

        Args:
            file_data: File metadata
            content: File content as bytes

        Returns:
            Saved FileRecord object

        Raises:
            Exception: If save operation fails
        """
        try:
            # Generate file_id (short UUID)
            file_id = str(uuid.uuid4())[:8]

            # Save file to S3
            self.s3_client.put_object(
                Bucket=file_data.s3_bucket,
                Key=file_data.s3_key,
                Body=content,
            )
            logger.info(f"Saved file to S3: s3://{file_data.s3_bucket}/{file_data.s3_key}")

            # Save metadata to MongoDB
            return self._save_file_metadata(file_id, file_data)

        except Exception as e:
            logger.error(f"Failed to save file: {e}")
            raise

    def track_existing_file(
        self,
        file_data: FileRecordCreate,
    ) -> FileRecord:
        """Track an existing S3 file in MongoDB (file already exists in S3).

        Use this when a file was created outside of FileStorageService
        (e.g., by sandbox via execute_code) and you just want to track it.

        Args:
            file_data: File metadata

        Returns:
            FileRecord object

        Raises:
            Exception: If tracking fails
        """
        try:
            # Generate file_id (short UUID)
            file_id = str(uuid.uuid4())[:8]

            # Verify file exists in S3 and get size if not provided
            if file_data.size_bytes == 0:
                try:
                    head_response = self.s3_client.head_object(
                        Bucket=file_data.s3_bucket, Key=file_data.s3_key
                    )
                    file_data.size_bytes = head_response.get("ContentLength", 0)
                except Exception as e:
                    logger.warning(f"Could not get file size from S3: {e}")

            # Save metadata to MongoDB (file already exists in S3)
            logger.info(f"Tracking existing S3 file: s3://{file_data.s3_bucket}/{file_data.s3_key}")
            return self._save_file_metadata(file_id, file_data)

        except Exception as e:
            logger.error(f"Failed to track existing file: {e}")
            raise

    def _save_file_metadata(self, file_id: str, file_data: FileRecordCreate) -> FileRecord:
        """Internal method to save file metadata to MongoDB.

        Args:
            file_id: Generated file ID
            file_data: File metadata

        Returns:
            FileRecord object
        """
        now = datetime.utcnow()
        file_doc = {
            "file_id": file_id,
            "user_id": file_data.user_id,
            "thread_id": file_data.thread_id,
            "file_type": file_data.file_type.value,
            "s3_bucket": file_data.s3_bucket,
            "s3_key": file_data.s3_key,
            "content_type": file_data.content_type,
            "size_bytes": file_data.size_bytes,
            "metadata": file_data.metadata,
            "created_at": now,
        }

        try:
            self.files_collection.insert_one(file_doc)
            logger.info(
                f"Saved file metadata: file_id={file_id}, type={file_data.file_type.value}, "
                f"s3_key={file_data.s3_key}"
            )
        except Exception as e:
            logger.error(f"Failed to insert file metadata into MongoDB: {e}")
            logger.error(f"Database: {self.db.name}, Collection: files")
            logger.error(f"File document: {file_doc}")
            raise

        return FileRecord(
            file_id=file_id,
            user_id=file_data.user_id,
            thread_id=file_data.thread_id,
            file_type=file_data.file_type,
            s3_bucket=file_data.s3_bucket,
            s3_key=file_data.s3_key,
            content_type=file_data.content_type,
            size_bytes=file_data.size_bytes,
            metadata=file_data.metadata,
            created_at=now,
        )

    def save_file_from_content(
        self,
        content: str,
        file_data: FileRecordCreate,
    ) -> FileRecord:
        """Save file from string content to S3 and metadata to MongoDB.

        Args:
            content: File content as string
            file_data: File metadata

        Returns:
            Saved FileRecord object
        """
        # Update size_bytes if not set
        if file_data.size_bytes == 0:
            file_data.size_bytes = len(content.encode("utf-8"))

        return self.save_file(file_data, content.encode("utf-8"))

    def save_file_from_dataframe(
        self,
        dataframe: pd.DataFrame,
        file_data: FileRecordCreate,
    ) -> FileRecord:
        """Save DataFrame as CSV to S3 and metadata to MongoDB.

        Convenience method for saving query results and data analyses.

        Args:
            dataframe: DataFrame to save as CSV
            file_data: File metadata (size_bytes will be calculated automatically)

        Returns:
            Saved FileRecord object
        """
        # Convert DataFrame to CSV
        csv_content = dataframe.to_csv(index=False)
        content_bytes = csv_content.encode("utf-8")

        # Update metadata with DataFrame info if not already set
        if "row_count" not in file_data.metadata:
            file_data.metadata["row_count"] = len(dataframe)
        if "column_count" not in file_data.metadata:
            file_data.metadata["column_count"] = len(dataframe.columns)
        if "columns" not in file_data.metadata:
            file_data.metadata["columns"] = dataframe.columns.tolist()

        # Update size_bytes
        file_data.size_bytes = len(content_bytes)

        return self.save_file(file_data, content_bytes)

    def get_by_file_id(self, file_id: str, user_id: Optional[str] = None) -> Optional[FileRecord]:
        """Get file record by file_id (with user_id authorization check).

        Args:
            file_id: File ID (short UUID)
            user_id: User ID for authorization (optional, but recommended)

        Returns:
            FileRecord if found and authorized, None otherwise
        """
        try:
            query = {"file_id": file_id}
            # CRITICAL: Filter by user_id if provided to prevent unauthorized access
            if user_id is not None:
                query["user_id"] = user_id

            doc = self.files_collection.find_one(query)
            if doc is None:
                return None

            return FileRecord(
                file_id=doc["file_id"],
                user_id=doc.get("user_id"),
                thread_id=doc.get("thread_id"),
                file_type=FileType(doc["file_type"]),
                s3_bucket=doc["s3_bucket"],
                s3_key=doc["s3_key"],
                content_type=doc["content_type"],
                size_bytes=doc["size_bytes"],
                metadata=doc.get("metadata", {}),
                created_at=doc["created_at"],
            )

        except Exception as e:
            logger.error(f"Failed to get file record: {e}")
            raise

    def get_file_content(self, file_id: str, user_id: Optional[str] = None) -> Optional[bytes]:
        """Retrieve file content from S3.

        Args:
            file_id: File ID (short UUID)
            user_id: User ID for authorization (optional, but recommended)

        Returns:
            File content as bytes, or None if not found or not authorized
        """
        try:
            file_record = self.get_by_file_id(file_id, user_id)
            if file_record is None:
                return None

            # Retrieve from S3
            response = self.s3_client.get_object(
                Bucket=file_record.s3_bucket, Key=file_record.s3_key
            )
            return response["Body"].read()

        except Exception as e:
            logger.error(f"Failed to get file content: {e}")
            raise

    def list_by_user(
        self,
        user_id: str,
        file_type: Optional[FileType] = None,
        content_type_pattern: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[FileRecord]:
        """List user's files.

        Args:
            user_id: User's unique identifier
            file_type: Optional filter by file type
            content_type_pattern: Optional filter by content type pattern (e.g., 'image' for image files)
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination

        Returns:
            List of FileRecord objects
        """
        try:
            query = {"user_id": user_id}
            if file_type is not None:
                query["file_type"] = file_type.value
            if content_type_pattern:
                # Use regex to match content types (e.g., 'image' matches 'png', 'jpg', etc.)
                query["content_type"] = {"$regex": content_type_pattern, "$options": "i"}

            cursor = (
                self.files_collection.find(query).sort("created_at", -1).skip(offset).limit(limit)
            )

            results = []
            for doc in cursor:
                results.append(
                    FileRecord(
                        file_id=doc["file_id"],
                        user_id=doc.get("user_id"),
                        thread_id=doc.get("thread_id"),
                        file_type=FileType(doc["file_type"]),
                        s3_bucket=doc["s3_bucket"],
                        s3_key=doc["s3_key"],
                        content_type=doc["content_type"],
                        size_bytes=doc["size_bytes"],
                        metadata=doc.get("metadata", {}),
                        created_at=doc["created_at"],
                    )
                )

            return results

        except Exception as e:
            logger.error(f"Failed to list files by user: {e}")
            raise

    def list_by_thread(
        self,
        thread_id: str,
        user_id: Optional[str] = None,
        file_type: Optional[FileType] = None,
        content_type_pattern: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[FileRecord]:
        """List files for a conversation thread.

        Args:
            thread_id: Thread ID (format: {user_id}:{conversation_id})
            user_id: User ID for authorization (optional but recommended)
            file_type: Optional filter by file type
            content_type_pattern: Optional filter by content type pattern
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination

        Returns:
            List of FileRecord objects
        """
        try:
            query = {"thread_id": thread_id}
            # CRITICAL: Filter by user_id if provided
            if user_id is not None:
                query["user_id"] = user_id
            if file_type is not None:
                query["file_type"] = file_type.value
            if content_type_pattern:
                query["content_type"] = {"$regex": content_type_pattern, "$options": "i"}

            cursor = (
                self.files_collection.find(query).sort("created_at", -1).skip(offset).limit(limit)
            )

            results = []
            for doc in cursor:
                results.append(
                    FileRecord(
                        file_id=doc["file_id"],
                        user_id=doc.get("user_id"),
                        thread_id=doc.get("thread_id"),
                        file_type=FileType(doc["file_type"]),
                        s3_bucket=doc["s3_bucket"],
                        s3_key=doc["s3_key"],
                        content_type=doc["content_type"],
                        size_bytes=doc["size_bytes"],
                        metadata=doc.get("metadata", {}),
                        created_at=doc["created_at"],
                    )
                )

            return results

        except Exception as e:
            logger.error(f"Failed to list files by thread: {e}")
            raise

    def list_by_threads_bulk(
        self,
        thread_ids: List[str],
        file_type: Optional[FileType] = None,
        content_type_pattern: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[FileRecord]:
        """List files for multiple conversation threads in a single query.

        Optimized bulk query using MongoDB $in operator to avoid N+1 query problem.

        Args:
            thread_ids: List of thread IDs (format: {user_id}:{conversation_id})
            file_type: Optional filter by file type
            content_type_pattern: Optional filter by content type pattern
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination

        Returns:
            List of FileRecord objects sorted by created_at descending
        """
        if not thread_ids:
            return []

        try:
            query: dict = {"thread_id": {"$in": thread_ids}}
            if file_type is not None:
                query["file_type"] = file_type.value
            if content_type_pattern:
                query["content_type"] = {"$regex": content_type_pattern, "$options": "i"}

            cursor = (
                self.files_collection.find(query).sort("created_at", -1).skip(offset).limit(limit)
            )

            results = []
            for doc in cursor:
                results.append(
                    FileRecord(
                        file_id=doc["file_id"],
                        user_id=doc.get("user_id"),
                        thread_id=doc.get("thread_id"),
                        file_type=FileType(doc["file_type"]),
                        s3_bucket=doc["s3_bucket"],
                        s3_key=doc["s3_key"],
                        content_type=doc["content_type"],
                        size_bytes=doc["size_bytes"],
                        metadata=doc.get("metadata", {}),
                        created_at=doc["created_at"],
                    )
                )

            logger.info(f"Bulk query returned {len(results)} files from {len(thread_ids)} threads")
            return results

        except Exception as e:
            logger.error(f"Failed to list files by threads bulk: {e}")
            raise

    def list_by_file_type(
        self,
        file_type: FileType,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[FileRecord]:
        """List files by file type.

        Args:
            file_type: File type to filter by
            user_id: Optional user ID filter
            limit: Maximum number of results to return

        Returns:
            List of FileRecord objects
        """
        try:
            query = {"file_type": file_type.value}
            if user_id is not None:
                query["user_id"] = user_id

            cursor = self.files_collection.find(query).sort("created_at", -1).limit(limit)

            results = []
            for doc in cursor:
                results.append(
                    FileRecord(
                        file_id=doc["file_id"],
                        user_id=doc.get("user_id"),
                        thread_id=doc.get("thread_id"),
                        file_type=FileType(doc["file_type"]),
                        s3_bucket=doc["s3_bucket"],
                        s3_key=doc["s3_key"],
                        content_type=doc["content_type"],
                        size_bytes=doc["size_bytes"],
                        metadata=doc.get("metadata", {}),
                        created_at=doc["created_at"],
                    )
                )

            return results

        except Exception as e:
            logger.error(f"Failed to list files by type: {e}")
            raise

    def delete_file(self, file_id: str, user_id: Optional[str] = None) -> bool:
        """Delete file from S3 and MongoDB.

        Args:
            file_id: File ID (short UUID)
            user_id: User ID for authorization (optional but recommended)

        Returns:
            True if deleted, False if not found or not authorized
        """
        try:
            # Get file record first to get S3 info
            file_record = self.get_by_file_id(file_id, user_id)
            if file_record is None:
                return False

            # Delete from S3
            try:
                self.s3_client.delete_object(Bucket=file_record.s3_bucket, Key=file_record.s3_key)
                logger.info(f"Deleted S3 file: s3://{file_record.s3_bucket}/{file_record.s3_key}")
            except Exception as e:
                logger.warning(f"Failed to delete S3 file: {e}")

            # Delete from MongoDB
            query = {"file_id": file_id}
            if user_id is not None:
                query["user_id"] = user_id

            delete_result = self.files_collection.delete_one(query)

            if delete_result.deleted_count > 0:
                logger.info(f"Deleted file record: file_id={file_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            raise

    def generate_download_url(
        self,
        file_id: str,
        user_id: Optional[str] = None,
        expires_in: int = 3600,
        use_cache: bool = True,
    ) -> Optional[str]:
        """Generate presigned S3 URL for downloading a file with optional caching.

        Args:
            file_id: File ID (short UUID)
            user_id: User ID for authorization (optional but recommended)
            expires_in: URL expiration time in seconds (default: 1 hour)
            use_cache: Whether to use URL caching (default: True)

        Returns:
            Presigned URL string, or None if file not found or not authorized
        """
        try:
            # Check cache first (if enabled)
            if use_cache:
                cached_url = self._get_cached_url(file_id)
                if cached_url:
                    logger.debug(f"Cache hit for file_id={file_id}")
                    return cached_url

            # Get file record with authorization check
            file_record = self.get_by_file_id(file_id, user_id)
            if file_record is None:
                logger.warning(f"File not found or not authorized: file_id={file_id}")
                return None

            # Generate presigned URL
            presigned_url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": file_record.s3_bucket,
                    "Key": file_record.s3_key,
                },
                ExpiresIn=expires_in,
            )

            # Cache the URL
            if use_cache:
                self._cache_url(file_id, presigned_url, expires_in)

            logger.info(f"Generated presigned URL for file_id={file_id}, expires in {expires_in}s")
            return presigned_url

        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise

    def _get_cached_url(self, file_id: str) -> Optional[str]:
        """Get cached presigned URL if valid.

        Args:
            file_id: File ID to look up

        Returns:
            Cached URL if valid, None otherwise
        """
        with _url_cache_lock:
            if file_id in _url_cache:
                url, expiry = _url_cache[file_id]
                if time.time() < expiry:
                    return url
                # Remove expired entry
                del _url_cache[file_id]
        return None

    def _cache_url(self, file_id: str, url: str, expires_in: int) -> None:
        """Cache a presigned URL with expiration.

        Args:
            file_id: File ID as cache key
            url: Presigned URL to cache
            expires_in: URL expiration time in seconds
        """
        # Calculate when to expire the cache (URL expiry minus buffer)
        cache_expiry = time.time() + expires_in - URL_CACHE_BUFFER_SECONDS
        with _url_cache_lock:
            _url_cache[file_id] = (url, cache_expiry)

    def generate_batch_download_urls(
        self,
        file_ids: List[str],
        user_id: Optional[str] = None,
        expires_in: int = 3600,
    ) -> Dict[str, Optional[str]]:
        """Generate presigned URLs for multiple files in batch.

        Optimized for bulk URL generation with caching support.
        Fetches file records in bulk from MongoDB to reduce round-trips.

        Args:
            file_ids: List of file IDs to generate URLs for
            user_id: User ID for authorization (optional)
            expires_in: URL expiration time in seconds (default: 1 hour)

        Returns:
            Dict mapping file_id to presigned URL (or None if not found/authorized)
        """
        if not file_ids:
            return {}

        results: Dict[str, Optional[str]] = {}
        uncached_ids: List[str] = []

        # Check cache first for all file_ids
        for file_id in file_ids:
            cached_url = self._get_cached_url(file_id)
            if cached_url:
                results[file_id] = cached_url
                logger.debug(f"Batch cache hit for file_id={file_id}")
            else:
                uncached_ids.append(file_id)

        if not uncached_ids:
            logger.info(f"Batch URL generation: all {len(file_ids)} URLs served from cache")
            return results

        try:
            # Fetch all uncached file records in bulk
            query = {"file_id": {"$in": uncached_ids}}
            if user_id is not None:
                query["user_id"] = user_id

            file_docs = list(self.files_collection.find(query))

            # Build a lookup map
            file_map: Dict[str, dict] = {doc["file_id"]: doc for doc in file_docs}

            # Generate presigned URLs for found files
            cache_entries = []
            for file_id in uncached_ids:
                if file_id not in file_map:
                    results[file_id] = None
                    continue

                doc = file_map[file_id]
                presigned_url = self.s3_client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": doc["s3_bucket"],
                        "Key": doc["s3_key"],
                    },
                    ExpiresIn=expires_in,
                )
                results[file_id] = presigned_url
                cache_entries.append((file_id, presigned_url))

            # Batch cache update
            cache_expiry = time.time() + expires_in - URL_CACHE_BUFFER_SECONDS
            with _url_cache_lock:
                for file_id, url in cache_entries:
                    _url_cache[file_id] = (url, cache_expiry)

            logger.info(
                f"Batch URL generation: {len(file_ids)} requested, "
                f"{len(file_ids) - len(uncached_ids)} from cache, "
                f"{len(cache_entries)} newly generated"
            )
            return results

        except Exception as e:
            logger.error(f"Failed to generate batch presigned URLs: {e}")
            raise

    def list_artifacts_with_conversation_metadata(
        self,
        user_id: str,
        thread_id: Optional[str] = None,
        file_type: Optional[FileType] = None,
        content_type_pattern: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ArtifactResponse]:
        """List artifacts with conversation metadata for display.

        Args:
            user_id: User's unique identifier (used for filtering when no thread_id)
            thread_id: Optional filter by thread ID (if provided, user_id is ignored
                      since authorization should be done by the caller)
            file_type: Optional filter by file type
            content_type_pattern: Optional filter by content type pattern
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination

        Returns:
            List of ArtifactResponse objects with conversation metadata
        """
        try:
            # Get files based on filter
            if thread_id:
                # When thread_id is provided, don't filter by user_id
                # Authorization should already be done by the caller (e.g., checking shared access)
                files = self.list_by_thread(
                    thread_id, None, file_type, content_type_pattern, limit, offset
                )
            else:
                files = self.list_by_user(user_id, file_type, content_type_pattern, limit, offset)

            # Extract unique conversation IDs from thread_ids
            conversation_ids = set()
            for file in files:
                if file.thread_id:
                    # Extract conversation_id from thread_id format: "user_id:conversation_id"
                    parts = file.thread_id.split(":", 1)
                    if len(parts) == 2:
                        conversation_ids.add(parts[1])

            # Fetch conversation metadata in bulk
            conversations_map = {}
            if conversation_ids:
                conversations_cursor = self.conversations_collection.find(
                    {"id": {"$in": list(conversation_ids)}}, {"id": 1, "title": 1}
                )
                for conv in conversations_cursor:
                    conversations_map[conv["id"]] = conv.get("title", "Untitled Conversation")

            # Build artifact responses with conversation metadata
            artifacts = []
            for file in files:
                conversation_id = None
                conversation_title = None

                if file.thread_id:
                    parts = file.thread_id.split(":", 1)
                    if len(parts) == 2:
                        conversation_id = parts[1]
                        conversation_title = conversations_map.get(conversation_id)

                artifacts.append(
                    ArtifactResponse(
                        file_id=file.file_id,
                        user_id=file.user_id,
                        thread_id=file.thread_id,
                        conversation_id=conversation_id,
                        conversation_title=conversation_title,
                        file_type=file.file_type,
                        s3_bucket=file.s3_bucket,
                        s3_key=file.s3_key,
                        content_type=file.content_type,
                        size_bytes=file.size_bytes,
                        metadata=file.metadata,
                        created_at=file.created_at,
                    )
                )

            return artifacts

        except Exception as e:
            logger.error(f"Failed to list artifacts with conversation metadata: {e}")
            raise

    def list_artifacts_by_threads_with_metadata(
        self,
        thread_ids: List[str],
        file_type: Optional[FileType] = None,
        content_type_pattern: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ArtifactResponse]:
        """List artifacts from multiple threads with conversation metadata (bulk query).

        Optimized for project-level queries that need artifacts from multiple conversations.
        Uses a single MongoDB $in query instead of N separate queries.

        Args:
            thread_ids: List of thread IDs to fetch artifacts from
            file_type: Optional filter by file type
            content_type_pattern: Optional filter by content type pattern
            limit: Maximum number of results to return
            offset: Number of results to skip for pagination

        Returns:
            List of ArtifactResponse objects with conversation metadata, sorted by created_at desc
        """
        if not thread_ids:
            return []

        try:
            # Single bulk query for all thread_ids
            files = self.list_by_threads_bulk(
                thread_ids, file_type, content_type_pattern, limit, offset
            )

            # Extract unique conversation IDs from thread_ids
            conversation_ids = set()
            for file in files:
                if file.thread_id:
                    parts = file.thread_id.split(":", 1)
                    if len(parts) == 2:
                        conversation_ids.add(parts[1])

            # Fetch conversation metadata in bulk
            conversations_map = {}
            if conversation_ids:
                conversations_cursor = self.conversations_collection.find(
                    {"id": {"$in": list(conversation_ids)}}, {"id": 1, "title": 1}
                )
                for conv in conversations_cursor:
                    conversations_map[conv["id"]] = conv.get("title", "Untitled Conversation")

            # Build artifact responses with conversation metadata
            artifacts = []
            for file in files:
                conversation_id = None
                conversation_title = None

                if file.thread_id:
                    parts = file.thread_id.split(":", 1)
                    if len(parts) == 2:
                        conversation_id = parts[1]
                        conversation_title = conversations_map.get(conversation_id)

                artifacts.append(
                    ArtifactResponse(
                        file_id=file.file_id,
                        user_id=file.user_id,
                        thread_id=file.thread_id,
                        conversation_id=conversation_id,
                        conversation_title=conversation_title,
                        file_type=file.file_type,
                        s3_bucket=file.s3_bucket,
                        s3_key=file.s3_key,
                        content_type=file.content_type,
                        size_bytes=file.size_bytes,
                        metadata=file.metadata,
                        created_at=file.created_at,
                    )
                )

            logger.info(
                f"Bulk artifacts query: {len(artifacts)} artifacts from {len(thread_ids)} threads"
            )
            return artifacts

        except Exception as e:
            logger.error(f"Failed to list artifacts by threads with metadata: {e}")
            raise
