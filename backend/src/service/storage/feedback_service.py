"""Message feedback management service with MongoDB."""

import logging
import uuid
from datetime import datetime
from typing import Optional

from src.config.settings import settings
from src.models.feedback import (
    ConversationFeedbackEntry,
    FeedbackType,
    MessageFeedback,
    MessageFeedbackCreate,
)
from src.service.database.connections.mongodb_connection import get_mongodb_database

logger = logging.getLogger(__name__)


class FeedbackService:
    """Service class for feedback CRUD operations with MongoDB.

    Feedback allows users to rate AI responses with thumbs up/down
    and optionally provide notes for evaluation purposes.
    """

    def __init__(self, db_name: Optional[str] = None):
        """Initialize FeedbackService with MongoDB database.

        Args:
            db_name: MongoDB database name (defaults to settings.mongodb_db_name)
        """
        if db_name is None:
            db_name = getattr(settings, "mongodb_db_name", "langgraph_checkpoints")
        self.db = get_mongodb_database(db_name)
        self.feedback_collection = self.db["feedback"]
        self.conversations_collection = self.db["conversations"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create indexes on feedback collection."""
        try:
            self.feedback_collection.create_index("feedback_id", unique=True)
            # Unique compound index: one feedback per message per user
            self.feedback_collection.create_index(
                [("user_id", 1), ("conversation_id", 1), ("message_index", 1)],
                unique=True,
            )
            self.feedback_collection.create_index([("user_id", 1), ("feedback_type", 1)])
            self.feedback_collection.create_index("conversation_id")
            logger.debug("Feedback collection indexes created/verified")
        except Exception as e:
            logger.warning(f"Failed to create feedback indexes: {e}")

    def create_or_update_feedback(
        self, user_id: str, feedback_data: MessageFeedbackCreate
    ) -> MessageFeedback:
        """Create or update feedback for a message (upsert behavior).

        Args:
            user_id: User who owns the feedback
            feedback_data: Feedback creation data

        Returns:
            Created or updated feedback object

        Raises:
            ValueError: If conversation not found or doesn't belong to user
            Exception: If database operation fails
        """
        try:
            # Verify conversation exists and belongs to user
            conversation = self.conversations_collection.find_one(
                {"conversation_id": feedback_data.conversation_id, "user_id": user_id}
            )
            if conversation is None:
                raise ValueError("Conversation not found or unauthorized")

            now = datetime.utcnow()

            # Check if feedback already exists for this message
            existing = self.feedback_collection.find_one(
                {
                    "user_id": user_id,
                    "conversation_id": feedback_data.conversation_id,
                    "message_index": feedback_data.message_index,
                }
            )

            if existing:
                # Update existing feedback
                self.feedback_collection.update_one(
                    {"feedback_id": existing["feedback_id"]},
                    {
                        "$set": {
                            "feedback_type": feedback_data.feedback_type.value,
                            "note": feedback_data.note,
                            "updated_at": now,
                        }
                    },
                )
                feedback_id = existing["feedback_id"]
                created_at = existing["created_at"]
                logger.info(f"Updated feedback {feedback_id} for user {user_id}")
            else:
                # Create new feedback
                feedback_id = str(uuid.uuid4())
                created_at = now

                feedback_doc = {
                    "feedback_id": feedback_id,
                    "user_id": user_id,
                    "conversation_id": feedback_data.conversation_id,
                    "message_index": feedback_data.message_index,
                    "feedback_type": feedback_data.feedback_type.value,
                    "note": feedback_data.note,
                    "created_at": created_at,
                    "updated_at": now,
                }

                self.feedback_collection.insert_one(feedback_doc)
                logger.info(
                    f"Created feedback {feedback_id} for user {user_id} "
                    f"on conversation {feedback_data.conversation_id}"
                )

            return MessageFeedback(
                id=feedback_id,
                user_id=user_id,
                conversation_id=feedback_data.conversation_id,
                message_index=feedback_data.message_index,
                feedback_type=FeedbackType(feedback_data.feedback_type.value),
                note=feedback_data.note,
                created_at=created_at,
                updated_at=now,
            )

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to create/update feedback: {e}")
            raise

    def get_message_feedback(
        self, user_id: str, conversation_id: str, message_index: int
    ) -> Optional[MessageFeedback]:
        """Get feedback for a specific message.

        Args:
            user_id: User's unique identifier
            conversation_id: Conversation's unique identifier
            message_index: Index of the message in conversation

        Returns:
            MessageFeedback if found, None otherwise
        """
        try:
            doc = self.feedback_collection.find_one(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_index": message_index,
                }
            )

            if doc is None:
                return None

            return MessageFeedback(
                id=doc["feedback_id"],
                user_id=doc["user_id"],
                conversation_id=doc["conversation_id"],
                message_index=doc["message_index"],
                feedback_type=FeedbackType(doc["feedback_type"]),
                note=doc.get("note"),
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
            )

        except Exception as e:
            logger.error(f"Failed to get message feedback: {e}")
            raise

    def list_conversation_feedback(
        self, user_id: str, conversation_id: str
    ) -> list[ConversationFeedbackEntry]:
        """List all feedback entries for a conversation (batch loading).

        Args:
            user_id: User's unique identifier
            conversation_id: Conversation's unique identifier

        Returns:
            List of lightweight feedback entries
        """
        try:
            cursor = self.feedback_collection.find(
                {"user_id": user_id, "conversation_id": conversation_id},
                {"feedback_id": 1, "message_index": 1, "feedback_type": 1},
            )

            return [
                ConversationFeedbackEntry(
                    feedback_id=doc["feedback_id"],
                    message_index=doc["message_index"],
                    feedback_type=FeedbackType(doc["feedback_type"]),
                )
                for doc in cursor
            ]

        except Exception as e:
            logger.error(f"Failed to list conversation feedback: {e}")
            return []

    def delete_feedback(self, feedback_id: str, user_id: str) -> bool:
        """Delete feedback if it belongs to the user.

        Args:
            feedback_id: Feedback's unique identifier
            user_id: User's unique identifier (for authorization)

        Returns:
            True if deleted, False if not found or not authorized
        """
        try:
            result = self.feedback_collection.delete_one(
                {"feedback_id": feedback_id, "user_id": user_id}
            )

            if result.deleted_count > 0:
                logger.info(f"Deleted feedback {feedback_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete feedback: {e}")
            raise

    def delete_feedback_by_message(
        self, user_id: str, conversation_id: str, message_index: int
    ) -> bool:
        """Delete feedback for a specific message.

        Args:
            user_id: User's unique identifier
            conversation_id: Conversation's unique identifier
            message_index: Index of the message in conversation

        Returns:
            True if deleted, False if not found
        """
        try:
            result = self.feedback_collection.delete_one(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_index": message_index,
                }
            )

            if result.deleted_count > 0:
                logger.info(
                    f"Deleted feedback for message {message_index} "
                    f"in conversation {conversation_id}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete feedback by message: {e}")
            raise
