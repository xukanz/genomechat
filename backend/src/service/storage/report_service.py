"""Report management service with MongoDB."""

import logging
import uuid
from datetime import datetime
from typing import Optional

from src.config.settings import settings
from src.models.report import Report, ReportCreate, ReportUpdate
from src.service.database.connections.mongodb_connection import get_mongodb_database

logger = logging.getLogger(__name__)


class ReportService:
    """Service class for report CRUD operations with MongoDB.

    Reports are bookmarked AI responses that users can save for later reference.
    They inherit the project from their source conversation.
    """

    def __init__(self, db_name: Optional[str] = None):
        """Initialize ReportService with MongoDB database.

        Args:
            db_name: MongoDB database name (defaults to settings.mongodb_db_name)
        """
        if db_name is None:
            db_name = getattr(settings, "mongodb_db_name", "langgraph_checkpoints")
        self.db = get_mongodb_database(db_name)
        self.reports_collection = self.db["reports"]
        self.conversations_collection = self.db["conversations"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create indexes on reports collection."""
        try:
            self.reports_collection.create_index("report_id", unique=True)
            self.reports_collection.create_index([("user_id", 1), ("created_at", -1)])
            self.reports_collection.create_index([("user_id", 1), ("project_id", 1)])
            self.reports_collection.create_index("conversation_id")
            logger.debug("Report collection indexes created/verified")
        except Exception as e:
            logger.warning(f"Failed to create report indexes: {e}")

    def create_report(self, user_id: str, report_data: ReportCreate) -> Report:
        """Create a new report from a bookmarked AI response.

        Args:
            user_id: User who owns the report
            report_data: Report creation data

        Returns:
            Created report object

        Raises:
            ValueError: If conversation not found or doesn't belong to user
            Exception: If database operation fails
        """
        try:
            # Verify conversation exists and belongs to user
            conversation = self.conversations_collection.find_one(
                {"conversation_id": report_data.conversation_id, "user_id": user_id}
            )
            if conversation is None:
                raise ValueError("Conversation not found or unauthorized")

            now = datetime.utcnow()
            report_id = str(uuid.uuid4())

            # Inherit project_id from conversation
            project_id = conversation.get("project_id")
            conversation_title = conversation.get("title", "Untitled")

            report_doc = {
                "report_id": report_id,
                "user_id": user_id,
                "conversation_id": report_data.conversation_id,
                "conversation_title": conversation_title,
                "project_id": project_id,
                "title": report_data.title,
                "content": report_data.content,
                "message_index": report_data.message_index,
                "created_at": now,
                "updated_at": now,
            }

            self.reports_collection.insert_one(report_doc)

            logger.info(
                f"Created report {report_id} for user {user_id} "
                f"from conversation {report_data.conversation_id}"
            )

            return Report(
                id=report_id,
                user_id=user_id,
                conversation_id=report_data.conversation_id,
                conversation_title=conversation_title,
                project_id=project_id,
                title=report_data.title,
                content=report_data.content,
                message_index=report_data.message_index,
                created_at=now,
                updated_at=now,
            )

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to create report: {e}")
            raise

    def list_user_reports(self, user_id: str, project_id: Optional[str] = None) -> list[Report]:
        """List all reports for a user, ordered by most recent first.

        Args:
            user_id: User's unique identifier
            project_id: Optional project ID to filter reports (includes shared access)

        Returns:
            List of report objects for the user (owned + shared project reports)
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
                # User has access - get all reports in this project
                query: dict = {"project_id": project_id}
            else:
                # No project specified - only return user's own reports
                query: dict = {"user_id": user_id}

            cursor = self.reports_collection.find(query).sort("created_at", -1)

            reports = []
            for doc in cursor:
                reports.append(
                    Report(
                        id=doc["report_id"],
                        user_id=doc["user_id"],
                        conversation_id=doc["conversation_id"],
                        conversation_title=doc.get("conversation_title", "Untitled"),
                        project_id=doc.get("project_id"),
                        title=doc["title"],
                        content=doc["content"],
                        message_index=doc["message_index"],
                        created_at=doc["created_at"],
                        updated_at=doc["updated_at"],
                    )
                )

            return reports

        except Exception as e:
            logger.error(f"Failed to list reports: {e}")
            raise

    def get_report(self, report_id: str, user_id: str) -> Optional[Report]:
        """Get a specific report if user has access (owner or shared project).

        Args:
            report_id: Report's unique identifier
            user_id: User's unique identifier (for authorization)

        Returns:
            Report object if found and user has access, None otherwise
        """
        try:
            # First try to get by user_id (owner case)
            doc = self.reports_collection.find_one({"report_id": report_id, "user_id": user_id})

            if doc is None:
                # Not the owner - check if user has shared access to the report's project
                doc = self.reports_collection.find_one({"report_id": report_id})
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

            return Report(
                id=doc["report_id"],
                user_id=doc["user_id"],
                conversation_id=doc["conversation_id"],
                conversation_title=doc.get("conversation_title", "Untitled"),
                project_id=doc.get("project_id"),
                title=doc["title"],
                content=doc["content"],
                message_index=doc["message_index"],
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
            )

        except Exception as e:
            logger.error(f"Failed to get report: {e}")
            raise

    def update_report(
        self, report_id: str, user_id: str, updates: ReportUpdate
    ) -> Optional[Report]:
        """Update report title.

        Args:
            report_id: Report's unique identifier
            user_id: User's unique identifier (for authorization)
            updates: Fields to update

        Returns:
            Updated report if found, None otherwise
        """
        try:
            now = datetime.utcnow()

            update_doc: dict = {"updated_at": now}
            if updates.title is not None:
                update_doc["title"] = updates.title

            result = self.reports_collection.update_one(
                {"report_id": report_id, "user_id": user_id},
                {"$set": update_doc},
            )

            if result.modified_count == 0:
                # Check if report exists but wasn't modified
                existing = self.reports_collection.find_one(
                    {"report_id": report_id, "user_id": user_id}
                )
                if existing is None:
                    return None

            return self.get_report(report_id, user_id)

        except Exception as e:
            logger.error(f"Failed to update report: {e}")
            raise

    def delete_report(self, report_id: str, user_id: str) -> bool:
        """Delete a report if it belongs to the user.

        Args:
            report_id: Report's unique identifier
            user_id: User's unique identifier (for authorization)

        Returns:
            True if deleted, False if not found or not authorized
        """
        try:
            result = self.reports_collection.delete_one(
                {"report_id": report_id, "user_id": user_id}
            )

            if result.deleted_count > 0:
                logger.info(f"Deleted report {report_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to delete report: {e}")
            raise

    def get_report_count_by_project(self, user_id: str, project_id: str) -> int:
        """Get the count of reports in a specific project.

        Args:
            user_id: User's unique identifier
            project_id: Project's unique identifier

        Returns:
            Count of reports in the project
        """
        try:
            count = self.reports_collection.count_documents(
                {"user_id": user_id, "project_id": project_id}
            )
            return count
        except Exception as e:
            logger.error(f"Failed to get report count: {e}")
            return 0

    def get_report_counts_by_projects(self, user_id: str, project_ids: list[str]) -> dict[str, int]:
        """Get report counts for multiple projects.

        Args:
            user_id: User's unique identifier
            project_ids: List of project IDs

        Returns:
            Dict mapping project_id to report count
        """
        try:
            pipeline = [
                {"$match": {"user_id": user_id, "project_id": {"$in": project_ids}}},
                {"$group": {"_id": "$project_id", "count": {"$sum": 1}}},
            ]
            results = list(self.reports_collection.aggregate(pipeline))
            return {result["_id"]: result["count"] for result in results}
        except Exception as e:
            logger.error(f"Failed to get report counts: {e}")
            return {}

    def check_report_exists(
        self, user_id: str, conversation_id: str, message_index: int
    ) -> Optional[str]:
        """Check if a report exists for a specific message.

        Args:
            user_id: User's unique identifier
            conversation_id: Conversation's unique identifier
            message_index: Index of the message in the conversation

        Returns:
            Report ID if exists, None otherwise
        """
        try:
            doc = self.reports_collection.find_one(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_index": message_index,
                },
                {"report_id": 1},
            )
            return doc["report_id"] if doc else None
        except Exception as e:
            logger.error(f"Failed to check report exists: {e}")
            return None

    def list_conversation_reports(self, user_id: str, conversation_id: str) -> list[dict[str, any]]:
        """List all reports for a specific conversation.

        Used for batch loading bookmark states.

        Args:
            user_id: User's unique identifier
            conversation_id: Conversation's unique identifier

        Returns:
            List of dicts with report_id and message_index
        """
        try:
            # Check if user has access to this conversation (owner or shared project)
            from src.service.storage.conversation_service import ConversationService

            conversation_service = ConversationService(db_name=self.db.name)
            conversation = conversation_service.get_conversation(conversation_id, user_id)
            if conversation is None:
                # User doesn't have access to this conversation
                return []

            # User has access - get all reports for this conversation (regardless of owner)
            cursor = self.reports_collection.find(
                {"conversation_id": conversation_id},
                {"report_id": 1, "message_index": 1},
            )
            return [
                {"report_id": doc["report_id"], "message_index": doc["message_index"]}
                for doc in cursor
            ]
        except Exception as e:
            logger.error(f"Failed to list conversation reports: {e}")
            return []
