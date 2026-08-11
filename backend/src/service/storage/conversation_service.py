"""Conversation management service with MongoDB."""

import json
import logging
import re
import threading
from datetime import datetime
from typing import List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.base import CheckpointTuple
from langgraph.checkpoint.mongodb import MongoDBSaver

from src.config.settings import settings
from src.models.conversation import Conversation, ConversationWithMessages
from src.service.database.connections.mongodb_connection import (
    get_mongodb_client,
    get_mongodb_database,
)
from src.service.llm import LLMService
from src.service.storage.file_storage_service import FileStorageService  # Uses batch URL generation

logger = logging.getLogger(__name__)

# Module-level flags for one-time initialization
_conversation_indexes_created = False
_conversation_indexes_lock = threading.Lock()


class ConversationService:
    """Service class for conversation metadata CRUD operations with MongoDB.

    Note: This only manages conversation metadata (title, timestamps).
    The actual conversation state is managed by LangGraph MongoDBSaver.
    """

    def __init__(self, db_name: Optional[str] = None):
        """Initialize ConversationService with MongoDB database.

        Args:
            db_name: MongoDB database name (defaults to settings.mongodb_db_name)
        """
        if db_name is None:
            db_name = getattr(settings, "mongodb_db_name", "langgraph_checkpoints")
        self.db = get_mongodb_database(db_name)
        self.conversations_collection = self.db["conversations"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create indexes on conversations collection (only once per application lifecycle).

        Uses module-level flag with thread-safe locking to ensure indexes
        are created only once, avoiding redundant MongoDB calls.
        """
        global _conversation_indexes_created

        if _conversation_indexes_created:
            return

        with _conversation_indexes_lock:
            # Double-check locking pattern
            if _conversation_indexes_created:
                return

            try:
                # Create unique index on conversation_id
                self.conversations_collection.create_index("conversation_id", unique=True)
                # Create compound index on user_id and created_at
                self.conversations_collection.create_index([("user_id", 1), ("created_at", -1)])
                # Create index on thread_id for checkpointer lookups
                self.conversations_collection.create_index("thread_id")
                # Create compound index on project_id and updated_at for project filtering
                self.conversations_collection.create_index([("project_id", 1), ("updated_at", -1)])
                # Create compound index on user_id and project_id
                self.conversations_collection.create_index([("user_id", 1), ("project_id", 1)])
                logger.info("Conversation collection indexes created/verified (one-time init)")
                _conversation_indexes_created = True
            except Exception as e:
                logger.warning(f"Failed to create conversation indexes: {e}")

    def _generate_thread_id(self, user_id: str, conversation_id: str) -> str:
        """Generate thread_id in format: {user_id}:{conversation_id}.

        Args:
            user_id: User's unique identifier
            conversation_id: Conversation's unique identifier

        Returns:
            Thread ID string
        """
        return f"{user_id}:{conversation_id}"

    def create_conversation(
        self, conversation_id: str, user_id: str, title: str, project_id: Optional[str] = None
    ) -> Conversation:
        """Create a new conversation metadata entry.

        Args:
            conversation_id: Unique conversation identifier (UUID)
            user_id: User who owns the conversation
            title: Conversation title (usually from first message)
            project_id: Optional project ID to associate with conversation

        Returns:
            Created conversation object

        Raises:
            ValueError: If conversation_id already exists
            Exception: If database operation fails

        Example:
            >>> service = ConversationService()
            >>> conv = service.create_conversation("conv-123", "user-456", "Research query", "proj-789")
        """
        try:
            # Check if conversation already exists
            existing = self.conversations_collection.find_one({"conversation_id": conversation_id})
            if existing:
                raise ValueError("Conversation ID already exists")

            now = datetime.utcnow()
            thread_id = self._generate_thread_id(user_id, conversation_id)

            # If no project_id provided, ensure default project exists
            if project_id is None:
                from src.service.storage.project_service import ProjectService

                project_service = ProjectService(db_name=self.db.name)
                default_project = project_service.ensure_default_project(user_id)
                project_id = default_project.id

            # Insert conversation
            conversation_doc = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "thread_id": thread_id,
                "title": title,
                "project_id": project_id,
                "created_at": now,
                "updated_at": now,
            }

            self.conversations_collection.insert_one(conversation_doc)

            # Update project conversation count
            from src.service.storage.project_service import ProjectService

            project_service = ProjectService(db_name=self.db.name)
            project_service._update_conversation_count(project_id)

            logger.info(
                f"Created conversation {conversation_id} for user {user_id} in project {project_id}"
            )

            return Conversation(
                id=conversation_id,
                user_id=user_id,
                title=title,
                project_id=project_id,
                created_at=now,
                updated_at=now,
            )

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to create conversation: {e}")
            raise

    def list_user_conversations(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Conversation]:
        """List conversations for a user, ordered by most recent first.

        Args:
            user_id: User's unique identifier
            project_id: Optional project ID to filter conversations
            limit: Maximum number of results to return (default 100)
            offset: Number of results to skip for pagination

        Returns:
            List of conversation objects for the user

        Example:
            >>> service = ConversationService()
            >>> conversations = service.list_user_conversations("user-123")
            >>> project_conversations = service.list_user_conversations("user-123", "proj-456")
            >>> paginated = service.list_user_conversations("user-123", limit=20, offset=0)
        """
        try:
            # If project_id is provided, check if user has access (owner or shared)
            if project_id is not None:
                from src.service.storage.project_service import ProjectService

                project_service = ProjectService(db_name=self.db.name)
                project = project_service.get_project(project_id, user_id)
                if project is None:
                    # User doesn't have access to this project
                    return []
                # User has access - get all conversations in this project
                query = {"project_id": project_id}
            else:
                # No project specified - only return user's own conversations
                query = {"user_id": user_id}

            cursor = (
                self.conversations_collection.find(query)
                .sort("updated_at", -1)
                .skip(offset)
                .limit(limit)
            )

            conversations = []
            for doc in cursor:
                conversations.append(
                    Conversation(
                        id=doc["conversation_id"],
                        user_id=doc["user_id"],
                        title=doc["title"],
                        project_id=doc.get("project_id"),
                        created_at=doc["created_at"],
                        updated_at=doc["updated_at"],
                    )
                )

            return conversations

        except Exception as e:
            logger.error(f"Failed to list conversations: {e}")
            raise

    def get_conversation(self, conversation_id: str, user_id: str) -> Optional[Conversation]:
        """Get a specific conversation if user has access (owner or shared project).

        Args:
            conversation_id: Conversation's unique identifier
            user_id: User's unique identifier (for authorization)

        Returns:
            Conversation object if found and user has access, None otherwise

        Example:
            >>> service = ConversationService()
            >>> conv = service.get_conversation("conv-123", "user-456")
        """
        try:
            # First try to get by user_id (owner case)
            doc = self.conversations_collection.find_one(
                {"conversation_id": conversation_id, "user_id": user_id}
            )

            if doc is None:
                # Not the owner - check if user has shared access to this conversation's project
                doc = self.conversations_collection.find_one({"conversation_id": conversation_id})
                if doc is None:
                    return None

                # Check if user has shared access to the project
                project_id = doc.get("project_id")
                if project_id:
                    from src.service.storage.project_service import ProjectService

                    project_service = ProjectService(db_name=self.db.name)
                    project = project_service.get_project(project_id, user_id)
                    if project is None:
                        # User doesn't have access to the project
                        return None
                else:
                    # No project - only owner can access
                    return None

            return Conversation(
                id=doc["conversation_id"],
                user_id=doc["user_id"],
                title=doc["title"],
                project_id=doc.get("project_id"),
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
            )

        except Exception as e:
            logger.error(f"Failed to get conversation: {e}")
            raise

    def update_timestamp(self, conversation_id: str, user_id: str) -> bool:
        """Update the updated_at timestamp for a conversation.

        Args:
            conversation_id: Conversation's unique identifier
            user_id: User's unique identifier (for authorization)

        Returns:
            True if updated, False if not found or not authorized

        Example:
            >>> service = ConversationService()
            >>> service.update_timestamp("conv-123", "user-456")
        """
        try:
            now = datetime.utcnow()

            # CRITICAL: Always filter by user_id
            result = self.conversations_collection.update_one(
                {"conversation_id": conversation_id, "user_id": user_id},
                {"$set": {"updated_at": now}},
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"Failed to update conversation timestamp: {e}")
            raise

    def update_conversation_title(self, conversation_id: str, user_id: str, title: str) -> bool:
        """Update conversation title.

        Args:
            conversation_id: Conversation's unique identifier
            user_id: User's unique identifier (for authorization)
            title: New title

        Returns:
            True if updated, False if not found or not authorized
        """
        try:
            now = datetime.utcnow()

            # CRITICAL: Always filter by user_id
            result = self.conversations_collection.update_one(
                {"conversation_id": conversation_id, "user_id": user_id},
                {"$set": {"title": title, "updated_at": now}},
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"Failed to update conversation title: {e}")
            raise

    async def auto_generate_and_update_title(
        self,
        conversation_id: str,
        user_id: str,
        user_message: str,
        assistant_message: str,
    ) -> bool:
        """Generate a concise title from conversation content and update the conversation.

        Uses a lightweight LLM to generate a title based on the first exchange.
        Designed to run asynchronously without blocking the response.

        Args:
            conversation_id: Conversation's unique identifier
            user_id: User's unique identifier
            user_message: The user's first message
            assistant_message: The assistant's first response

        Returns:
            True if title was generated and updated successfully, False otherwise
        """
        logger.info(
            f"🚀 Starting auto-title generation for conversation {conversation_id}, user {user_id}"
        )
        try:
            # Use lightweight model for fast title generation (Haiku 4.5)
            logger.debug("Initializing LLM for title generation...")
            llm = LLMService.get_llm_by_provider(
                provider="portkey_bedrock",
                model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                temperature=0.7,
                streaming=False,
            )
            logger.debug("✅ LLM initialized")

            # Create prompt for title generation
            system_prompt = """You are a title generator. Generate a concise, descriptive title (3-8 words) for a conversation based on the first exchange.

The title should:
- Capture the main topic or intent
- Be specific and informative
- Use natural language (not just keywords)
- Be concise (3-8 words maximum)

Examples:
- "Analyzing TCR diversity patterns"
- "SQL query for vaccine data"
- "Comparing immune responses in studies"
- "Creating visualization of antibody sequences"

Only respond with the title, nothing else."""

            user_prompt = f"""User: {user_message[:500]}

Assistant: {assistant_message[:500]}

Generate a concise title for this conversation:"""

            # Generate title
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            logger.debug("📝 Calling LLM to generate title...")
            response = await llm.ainvoke(messages)
            generated_title = response.content.strip()
            logger.debug(f"🤖 LLM response: {generated_title}")

            # Remove quotes if present
            generated_title = generated_title.strip('"').strip("'")

            # Fallback to truncated user message if generation fails
            if not generated_title or len(generated_title) > 100:
                logger.warning(
                    f"Generated title invalid (empty or >100 chars), using fallback: {user_message[:100]}"
                )
                generated_title = user_message[:100]

            logger.info(
                f"✨ Auto-generated title for conversation {conversation_id}: '{generated_title}'"
            )

            # Update the conversation title
            logger.debug("💾 Updating conversation title in database...")
            result = self.update_conversation_title(conversation_id, user_id, generated_title)

            if result:
                logger.info(f"✅ Successfully updated title for conversation {conversation_id}")
            else:
                logger.warning("⚠️  Failed to update title - conversation not found or unauthorized")

            return result

        except Exception as e:
            logger.error(
                f"❌ Failed to auto-generate conversation title for {conversation_id}: {e}",
                exc_info=True,
            )
            return False

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Delete a conversation if it belongs to the user.

        Args:
            conversation_id: Conversation's unique identifier
            user_id: User's unique identifier (for authorization)

        Returns:
            True if deleted, False if not found or not authorized

        Example:
            >>> service = ConversationService()
            >>> service.delete_conversation("conv-123", "user-456")
        """
        try:
            # CRITICAL: Always filter by user_id to prevent unauthorized deletion
            result = self.conversations_collection.delete_one(
                {"conversation_id": conversation_id, "user_id": user_id}
            )

            if result.deleted_count > 0:
                logger.info(f"Deleted conversation {conversation_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete conversation: {e}")
            raise

    async def get_conversation_history(
        self, conversation_id: str, user_id: str
    ) -> Optional[ConversationWithMessages]:
        """Get conversation with full message history from checkpointer.

        Args:
            conversation_id: Conversation's unique identifier
            user_id: User's unique identifier (for authorization)

        Returns:
            ConversationWithMessages with full message history, or None if not found

        Raises:
            Exception: If checkpointer operation fails

        Example:
            >>> service = ConversationService()
            >>> conv = await service.get_conversation_history("conv-123", "user-456")
            >>> print(len(conv.messages))
            15
        """
        try:
            # CRITICAL: First verify user has access (owner or shared project)
            conversation = self.get_conversation(conversation_id, user_id)
            if conversation is None:
                return None

            # Get thread_id using the conversation OWNER's user_id (not the requesting user)
            # This is critical because thread_id format is {owner_user_id}:{conversation_id}
            thread_id = self._generate_thread_id(conversation.user_id, conversation_id)
            config = {"configurable": {"thread_id": thread_id}}

            # Get state from MongoDB checkpointer
            client = get_mongodb_client()
            db_name = getattr(settings, "mongodb_db_name", "langgraph_checkpoints")
            checkpointer = MongoDBSaver(client, db_name=db_name)

            try:
                state: Optional[CheckpointTuple] = await checkpointer.aget_tuple(config)  # type: ignore[arg-type]
                if state is None:
                    # No checkpoint found - return empty messages
                    return ConversationWithMessages(**conversation.model_dump(), messages=[])

                # Extract messages from checkpoint
                raw_messages = state.checkpoint.get("channel_values", {}).get("messages", [])
                logger.info(f"Found {len(raw_messages)} messages for thread_id: {thread_id}")

                # Convert messages to dictionaries
                message_dicts = []
                for msg in raw_messages:
                    if hasattr(msg, "dict"):
                        msg_dict = msg.dict()
                    elif hasattr(msg, "model_dump"):
                        msg_dict = msg.model_dump()
                    else:
                        msg_dict = {"content": str(msg), "type": "unknown"}
                    message_dicts.append(msg_dict)

                # Load file attachments for this conversation (use owner's user_id for thread lookup)
                file_attachments = await self._load_file_attachments(
                    conversation_id, conversation.user_id
                )

                # Attach files to coder agent messages by parsing S3_FILE markers
                message_dicts = self._attach_files_to_messages(message_dicts, file_attachments)

                # Compute token usage from checkpoint messages
                # Same logic as chat.py end event — reuses count_tokens_approximately
                token_usage = None
                try:
                    from langchain.agents.middleware.summarization import (
                        count_tokens_approximately,
                    )

                    estimated_tokens = count_tokens_approximately(raw_messages)
                    max_tokens = int(
                        settings.context_model_max_tokens
                        * settings.context_summary_trigger_fraction
                    )
                    token_usage = {
                        "estimated_tokens": estimated_tokens,
                        "max_tokens": max_tokens,
                        "usage_pct": round((estimated_tokens / max_tokens) * 100, 1)
                        if max_tokens > 0
                        else 0,
                    }
                except Exception as e:
                    logger.warning(f"Failed to estimate token usage: {e}")

                return ConversationWithMessages(
                    **conversation.model_dump(),
                    messages=message_dicts,
                    token_usage=token_usage,
                )
            except Exception as e:
                logger.warning(f"No checkpoint found for {thread_id}: {e}")
                # Return conversation with empty messages if no checkpoint yet
                return ConversationWithMessages(**conversation.model_dump(), messages=[])

        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            raise

    async def _load_file_attachments(self, conversation_id: str, user_id: str) -> list[dict]:
        """Load file attachments from MongoDB files collection for this conversation.

        Uses batch URL generation for optimal performance.

        Args:
            conversation_id: Conversation ID
            user_id: User ID

        Returns:
            List of file metadata dicts with presigned URLs
        """
        try:
            file_service = FileStorageService()
            # Get all files for this conversation using full thread_id
            thread_id = f"{user_id}:{conversation_id}"
            files = file_service.list_by_thread(thread_id=thread_id, user_id=user_id)

            if not files:
                return []

            # Generate presigned URLs in batch (single API call instead of N calls)
            file_ids = [f.file_id for f in files]
            url_map = file_service.generate_batch_download_urls(
                file_ids=file_ids,
                user_id=user_id,
                expires_in=3600,  # 1 hour
            )

            # Build file attachments with presigned URLs
            file_attachments = []
            for file_record in files:
                presigned_url = url_map.get(file_record.file_id)
                if not presigned_url:
                    logger.warning(f"No URL generated for file {file_record.file_id}")
                    continue

                # Extract filename from s3_key (e.g., "users/.../file.png" -> "file.png")
                filename = file_record.s3_key.split("/")[-1]

                # Determine if it's an image based on content_type or file extension
                content_type = file_record.content_type
                is_image = (
                    content_type.startswith("image/") if content_type else False
                ) or content_type in ["png", "jpg", "jpeg", "gif", "webp", "svg"]

                file_attachments.append(
                    {
                        "file_id": file_record.file_id,
                        "filename": filename,
                        "s3_bucket": file_record.s3_bucket,
                        "s3_key": file_record.s3_key,
                        "content_type": file_record.content_type,
                        "file_type": file_record.file_type.value
                        if hasattr(file_record.file_type, "value")
                        else str(file_record.file_type),
                        "url": presigned_url,
                        "is_image": is_image,
                        "created_at": file_record.created_at.isoformat()
                        if file_record.created_at
                        else None,
                    }
                )

            logger.info(
                f"Loaded {len(file_attachments)} file attachments for conversation {conversation_id} (batch URLs)"
            )
            return file_attachments

        except Exception as e:
            logger.error(f"Failed to load file attachments: {e}")
            return []

    def _attach_files_to_messages(self, messages: list[dict], files: list[dict]) -> list[dict]:
        """Attach files to coder agent messages by parsing S3_FILE markers or directly to AI messages.

        Args:
            messages: List of message dicts from checkpoint
            files: List of file attachment dicts with presigned URLs

        Returns:
            Messages with files attached
        """
        logger.info(
            f"[_attach_files_to_messages] Called with {len(messages)} messages and {len(files)} files"
        )
        logger.info(
            f"[_attach_files_to_messages] Files: {[{'id': f.get('file_id'), 'is_image': f.get('is_image'), 'content_type': f.get('content_type')} for f in files]}"
        )

        # Filter to only images
        image_files = [f for f in files if f.get("is_image", False)]
        logger.info(f"[_attach_files_to_messages] Filtered to {len(image_files)} image files")

        if not image_files:
            return messages

        # Create a map of S3 keys to file metadata for quick lookup
        files_by_key = {f["s3_key"]: f for f in files}

        # Try to attach files by parsing S3_FILE markers first
        found_markers = False
        for msg in messages:
            # Only process HumanMessage from coder agent
            if msg.get("type") != "human" or msg.get("name") != "coder":
                continue

            content = msg.get("content", "")
            if not content or not isinstance(content, str):
                continue

            # Find all S3_FILE markers in the message content
            # Pattern: S3_FILE[{"bucket": "...", "key": "..."}]
            pattern = r"S3_FILE\[(\{[^\}]+\})\]"
            matches = re.findall(pattern, content)

            if not matches:
                continue

            found_markers = True
            # Parse S3 file references and attach metadata
            msg_files = []
            for match in matches:
                try:
                    s3_ref = json.loads(match)
                    s3_key = s3_ref.get("key")

                    if s3_key and s3_key in files_by_key:
                        file_data = files_by_key[s3_key]
                        # Only include images
                        if file_data.get("is_image", False):
                            msg_files.append(
                                {
                                    "id": file_data["file_id"],
                                    "filename": file_data["filename"],
                                    "url": file_data["url"],
                                    "fileType": file_data["file_type"],
                                    "contentType": file_data["content_type"],
                                    "isImage": file_data["is_image"],
                                    "agent": "coder",
                                    "timestamp": file_data["created_at"],
                                }
                            )
                except Exception as e:
                    logger.warning(f"Failed to parse S3_FILE marker: {e}")
                    continue

            if msg_files:
                msg["files"] = msg_files
                logger.debug(f"Attached {len(msg_files)} files to coder message")

        # If no markers found, attach all images to the last AI message
        if not found_markers and image_files:
            logger.info(
                f"No S3_FILE markers found, attaching {len(image_files)} images to last AI message"
            )
            for msg in reversed(messages):
                if msg.get("type") == "ai":
                    msg["files"] = [
                        {
                            "id": f["file_id"],
                            "filename": f["filename"],
                            "url": f["url"],
                            "fileType": f["file_type"],
                            "contentType": f["content_type"],
                            "isImage": f["is_image"],
                            "agent": "coder",
                            "timestamp": f["created_at"],
                        }
                        for f in image_files
                    ]
                    logger.info(
                        f"✅ Attached {len(image_files)} images to AI message (type={msg.get('type')}, id={msg.get('id', 'N/A')})"
                    )
                    break
            else:
                logger.warning(f"⚠️ Could not find AI message to attach {len(image_files)} images")

        logger.info(
            f"Returning {len(messages)} messages, {sum(1 for m in messages if m.get('files'))} with files"
        )
        return messages
