"""Project management service with MongoDB."""

import logging
import uuid
from datetime import datetime
from typing import Optional

from src.config.settings import settings
from src.models.project import Project, ProjectCreate, ProjectShare, ProjectUpdate
from src.models.snippet import Snippet, SnippetCreate, SnippetUpdate
from src.models.user import UserSummary
from src.service.database.connections.mongodb_connection import get_mongodb_database

logger = logging.getLogger(__name__)


class ProjectService:
    """Service class for project CRUD operations with MongoDB."""

    def __init__(self, db_name: Optional[str] = None):
        """Initialize ProjectService with MongoDB database."""
        if db_name is None:
            db_name = getattr(settings, "mongodb_db_name", "langgraph_checkpoints")
        self.db = get_mongodb_database(db_name)
        self.projects_collection = self.db["projects"]
        self.conversations_collection = self.db["conversations"]
        self.files_collection = self.db["files"]
        self.reports_collection = self.db["reports"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create indexes on projects collection."""
        try:
            self.projects_collection.create_index("project_id", unique=True)
            self.projects_collection.create_index([("user_id", 1), ("created_at", -1)])
            self.projects_collection.create_index([("user_id", 1), ("is_default", 1)])
            # Index for finding shared projects
            self.projects_collection.create_index("shares.user_id")
            logger.debug("Project collection indexes created/verified")
        except Exception as e:
            logger.warning(f"Failed to create project indexes: {e}")

    def ensure_default_project(self, user_id: str) -> Project:
        """Ensure user has a default 'All Chats' project."""
        existing = self.projects_collection.find_one({"user_id": user_id, "is_default": True})

        if existing:
            # Calculate artifact and report counts
            project_id = existing["project_id"]
            artifact_counts = self._get_artifact_counts_by_project(user_id, [project_id])
            artifact_count = artifact_counts.get(project_id, 0)
            report_counts = self._get_report_counts_by_project(user_id, [project_id])
            report_count = report_counts.get(project_id, 0)

            return Project(
                id=project_id,
                user_id=existing["user_id"],
                name=existing["name"],
                description=existing.get("description"),
                color=existing.get("color"),
                created_at=existing["created_at"],
                updated_at=existing["updated_at"],
                is_default=existing["is_default"],
                conversation_count=existing.get("conversation_count", 0),
                artifact_count=artifact_count,
                report_count=report_count,
                last_conversation_at=existing.get("last_conversation_at"),
            )

        # Create default project
        now = datetime.utcnow()
        project_id = str(uuid.uuid4())

        project_doc = {
            "project_id": project_id,
            "user_id": user_id,
            "name": "All Chats",
            "description": "Default project for all conversations",
            "color": None,
            "created_at": now,
            "updated_at": now,
            "is_default": True,
            "conversation_count": 0,
            "last_conversation_at": None,
        }

        self.projects_collection.insert_one(project_doc)
        logger.info(f"Created default project for user {user_id}")

        return Project(
            id=project_id,
            user_id=user_id,
            name="All Chats",
            description="Default project for all conversations",
            color=None,
            created_at=now,
            updated_at=now,
            is_default=True,
            conversation_count=0,
            artifact_count=0,
            last_conversation_at=None,
        )

    def create_project(self, user_id: str, project_data: ProjectCreate) -> Project:
        """Create a new project."""
        try:
            now = datetime.utcnow()
            project_id = str(uuid.uuid4())

            project_doc = {
                "project_id": project_id,
                "user_id": user_id,
                "name": project_data.name,
                "description": project_data.description,
                "color": project_data.color,
                "created_at": now,
                "updated_at": now,
                "is_default": False,
                "conversation_count": 0,
                "last_conversation_at": None,
            }

            self.projects_collection.insert_one(project_doc)
            logger.info(f"Created project {project_id} for user {user_id}")

            return Project(
                id=project_id,
                user_id=user_id,
                name=project_data.name,
                description=project_data.description,
                color=project_data.color,
                created_at=now,
                updated_at=now,
                is_default=False,
                conversation_count=0,
                last_conversation_at=None,
            )
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            raise

    def list_user_projects(self, user_id: str) -> list[Project]:
        """List all projects user owns OR has shared access to."""
        try:
            # Include both owned and shared projects
            cursor = self.projects_collection.find(
                {
                    "$or": [
                        {"user_id": user_id},  # Owned
                        {"shares.user_id": user_id},  # Shared with user
                    ]
                }
            ).sort("updated_at", -1)

            projects = []
            project_ids = []
            owner_ids = set()

            for doc in cursor:
                project_id = doc["project_id"]
                project_ids.append(project_id)
                owner_ids.add(doc["user_id"])

                is_owner = doc["user_id"] == user_id
                shares = []
                if is_owner:
                    # Only show shares to the owner
                    shares = [
                        ProjectShare(
                            user_id=s["user_id"],
                            user_email=s["user_email"],
                            user_name=s.get("user_name"),
                            shared_by=s["shared_by"],
                            shared_at=s["shared_at"],
                        )
                        for s in doc.get("shares", [])
                    ]

                projects.append(
                    Project(
                        id=project_id,
                        user_id=doc["user_id"],
                        name=doc["name"],
                        description=doc.get("description"),
                        color=doc.get("color"),
                        created_at=doc["created_at"],
                        updated_at=doc["updated_at"],
                        is_default=doc.get("is_default", False),
                        conversation_count=doc.get("conversation_count", 0),
                        artifact_count=0,  # Will be calculated below
                        last_conversation_at=doc.get("last_conversation_at"),
                        shares=shares,
                        is_owner=is_owner,
                        is_shared=not is_owner,
                    )
                )

            # Calculate artifact and report counts for owned projects only
            # For shared projects, we need to use the owner's user_id
            for project in projects:
                if project.is_owner:
                    artifact_counts = self._get_artifact_counts_by_project(user_id, [project.id])
                    report_counts = self._get_report_counts_by_project(user_id, [project.id])
                else:
                    # For shared projects, get counts using the owner's user_id
                    artifact_counts = self._get_artifact_counts_by_project(
                        project.user_id, [project.id]
                    )
                    report_counts = self._get_report_counts_by_project(
                        project.user_id, [project.id]
                    )
                project.artifact_count = artifact_counts.get(project.id, 0)
                project.report_count = report_counts.get(project.id, 0)

            return projects
        except Exception as e:
            logger.error(f"Failed to list projects: {e}")
            raise

    def _get_artifact_counts_by_project(
        self, user_id: str, project_ids: list[str]
    ) -> dict[str, int]:
        """Get artifact counts for each project using optimized aggregation.

        Only counts image files (png, jpg, jpeg, gif, svg, webp).
        """
        try:
            # Single aggregation pipeline to get artifact counts per project
            pipeline = [
                # Match conversations for this user in these projects
                {"$match": {"user_id": user_id, "project_id": {"$in": project_ids}}},
                # Create thread_id field
                {"$addFields": {"thread_id": {"$concat": [user_id, ":", "$conversation_id"]}}},
                # Lookup artifacts (files) for each conversation
                {
                    "$lookup": {
                        "from": "files",
                        "localField": "thread_id",
                        "foreignField": "thread_id",
                        "as": "artifacts",
                    }
                },
                # Filter artifacts to only include images
                {
                    "$addFields": {
                        "image_artifacts": {
                            "$filter": {
                                "input": "$artifacts",
                                "as": "artifact",
                                "cond": {
                                    "$in": [
                                        "$$artifact.content_type",
                                        ["png", "jpg", "jpeg", "gif", "svg", "webp"],
                                    ]
                                },
                            }
                        }
                    }
                },
                # Group by project and count image artifacts
                {
                    "$group": {
                        "_id": "$project_id",
                        "artifact_count": {"$sum": {"$size": "$image_artifacts"}},
                    }
                },
            ]

            results = list(self.conversations_collection.aggregate(pipeline))

            # Convert to dict
            artifact_counts = {result["_id"]: result["artifact_count"] for result in results}

            return artifact_counts
        except Exception as e:
            logger.warning(f"Failed to calculate artifact counts: {e}")
            return {}

    def _get_report_counts_by_project(self, user_id: str, project_ids: list[str]) -> dict[str, int]:
        """Get report counts for each project."""
        try:
            pipeline = [
                {"$match": {"user_id": user_id, "project_id": {"$in": project_ids}}},
                {"$group": {"_id": "$project_id", "count": {"$sum": 1}}},
            ]
            results = list(self.reports_collection.aggregate(pipeline))
            return {result["_id"]: result["count"] for result in results}
        except Exception as e:
            logger.warning(f"Failed to calculate report counts: {e}")
            return {}

    def get_project(self, project_id: str, user_id: str) -> Optional[Project]:
        """Get a project by ID if user owns it OR has shared access."""
        try:
            # Allow access if user owns or has shared access
            doc = self.projects_collection.find_one(
                {
                    "project_id": project_id,
                    "$or": [
                        {"user_id": user_id},
                        {"shares.user_id": user_id},
                    ],
                }
            )

            if not doc:
                return None

            is_owner = doc["user_id"] == user_id
            owner_id = doc["user_id"]

            # Calculate counts using owner's user_id
            artifact_counts = self._get_artifact_counts_by_project(owner_id, [project_id])
            artifact_count = artifact_counts.get(project_id, 0)
            report_counts = self._get_report_counts_by_project(owner_id, [project_id])
            report_count = report_counts.get(project_id, 0)

            # Only show shares to the owner
            shares = []
            if is_owner:
                shares = [
                    ProjectShare(
                        user_id=s["user_id"],
                        user_email=s["user_email"],
                        user_name=s.get("user_name"),
                        shared_by=s["shared_by"],
                        shared_at=s["shared_at"],
                    )
                    for s in doc.get("shares", [])
                ]

            return Project(
                id=doc["project_id"],
                user_id=doc["user_id"],
                name=doc["name"],
                description=doc.get("description"),
                color=doc.get("color"),
                created_at=doc["created_at"],
                updated_at=doc["updated_at"],
                is_default=doc.get("is_default", False),
                conversation_count=doc.get("conversation_count", 0),
                artifact_count=artifact_count,
                report_count=report_count,
                last_conversation_at=doc.get("last_conversation_at"),
                shares=shares,
                is_owner=is_owner,
                is_shared=not is_owner,
                snippets=doc.get("snippets", []),
            )
        except Exception as e:
            logger.error(f"Failed to get project: {e}")
            raise

    def update_project(self, project_id: str, user_id: str, updates: ProjectUpdate) -> bool:
        """Update project metadata."""
        try:
            update_doc = {"updated_at": datetime.utcnow()}

            if updates.name is not None:
                update_doc["name"] = updates.name
            if updates.description is not None:
                update_doc["description"] = updates.description
            if updates.color is not None:
                update_doc["color"] = updates.color

            result = self.projects_collection.update_one(
                {"project_id": project_id, "user_id": user_id}, {"$set": update_doc}
            )

            if result.modified_count > 0:
                logger.info(f"Updated project {project_id}")
                return True

            return False
        except Exception as e:
            logger.error(f"Failed to update project: {e}")
            raise

    def delete_project(self, project_id: str, user_id: str) -> bool:
        """Delete a project and move conversations to default project."""
        try:
            # Cannot delete default project
            project = self.get_project(project_id, user_id)
            if not project or project.is_default:
                return False

            # Get default project
            default_project = self.ensure_default_project(user_id)

            # Move all conversations to default project
            self.conversations_collection.update_many(
                {"project_id": project_id, "user_id": user_id},
                {"$set": {"project_id": default_project.id}},
            )

            # Delete project
            result = self.projects_collection.delete_one(
                {"project_id": project_id, "user_id": user_id}
            )

            # Update conversation counts
            self._update_conversation_count(default_project.id)

            if result.deleted_count > 0:
                logger.info(f"Deleted project {project_id}")
                return True

            return False
        except Exception as e:
            logger.error(f"Failed to delete project: {e}")
            raise

    def move_conversation_to_project(
        self, conversation_id: str, target_project_id: str, user_id: str
    ) -> bool:
        """Move a conversation to a different project."""
        try:
            # Verify project exists and belongs to user
            project = self.get_project(target_project_id, user_id)
            if not project:
                return False

            # Get current project_id
            conv = self.conversations_collection.find_one(
                {"conversation_id": conversation_id, "user_id": user_id}
            )

            if not conv:
                return False

            old_project_id = conv.get("project_id")

            # Move conversation
            result = self.conversations_collection.update_one(
                {"conversation_id": conversation_id, "user_id": user_id},
                {"$set": {"project_id": target_project_id}},
            )

            # Update conversation counts
            if old_project_id:
                self._update_conversation_count(old_project_id)
            self._update_conversation_count(target_project_id)

            if result.modified_count > 0:
                logger.info(f"Moved conversation {conversation_id} to project {target_project_id}")
                return True

            return False
        except Exception as e:
            logger.error(f"Failed to move conversation: {e}")
            raise

    def _update_conversation_count(self, project_id: str) -> None:
        """Update denormalized conversation count for a project."""
        try:
            count = self.conversations_collection.count_documents({"project_id": project_id})

            # Get most recent conversation timestamp
            latest_conv = self.conversations_collection.find_one(
                {"project_id": project_id}, sort=[("updated_at", -1)]
            )

            last_conversation_at = latest_conv["updated_at"] if latest_conv else None

            self.projects_collection.update_one(
                {"project_id": project_id},
                {
                    "$set": {
                        "conversation_count": count,
                        "last_conversation_at": last_conversation_at,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )
        except Exception as e:
            logger.warning(f"Failed to update conversation count: {e}")

    # =========================================================================
    # Project Sharing Methods
    # =========================================================================

    def share_project(
        self,
        project_id: str,
        owner_id: str,
        target_user_id: str,
        user_info: UserSummary,
    ) -> ProjectShare:
        """Share a project with another user (owner only)."""
        try:
            # Verify caller is the owner
            doc = self.projects_collection.find_one({"project_id": project_id, "user_id": owner_id})

            if not doc:
                raise ValueError("Project not found or you are not the owner")

            # Cannot share default project
            if doc.get("is_default", False):
                raise ValueError("Cannot share the default project")

            # Cannot share with yourself
            if target_user_id == owner_id:
                raise ValueError("Cannot share project with yourself")

            # Check if already shared with this user
            existing_shares = doc.get("shares", [])
            for share in existing_shares:
                if share["user_id"] == target_user_id:
                    raise ValueError("Project already shared with this user")

            now = datetime.utcnow()
            share_doc = {
                "user_id": target_user_id,
                "user_email": user_info.email,
                "user_name": user_info.name,
                "shared_by": owner_id,
                "shared_at": now,
            }

            self.projects_collection.update_one(
                {"project_id": project_id},
                {
                    "$push": {"shares": share_doc},
                    "$set": {"updated_at": now},
                },
            )

            logger.info(f"Shared project {project_id} with user {target_user_id}")

            return ProjectShare(
                user_id=target_user_id,
                user_email=user_info.email,
                user_name=user_info.name,
                shared_by=owner_id,
                shared_at=now,
            )
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to share project: {e}")
            raise

    def remove_share(self, project_id: str, owner_id: str, target_user_id: str) -> bool:
        """Remove a user's access to a shared project (owner only)."""
        try:
            # Verify caller is the owner
            doc = self.projects_collection.find_one({"project_id": project_id, "user_id": owner_id})

            if not doc:
                raise ValueError("Project not found or you are not the owner")

            result = self.projects_collection.update_one(
                {"project_id": project_id},
                {
                    "$pull": {"shares": {"user_id": target_user_id}},
                    "$set": {"updated_at": datetime.utcnow()},
                },
            )

            if result.modified_count > 0:
                logger.info(f"Removed share for user {target_user_id} from project {project_id}")
                return True

            return False
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to remove share: {e}")
            raise

    def list_project_shares(self, project_id: str, user_id: str) -> list[ProjectShare]:
        """List all shares for a project (owner only)."""
        try:
            # Verify caller is the owner
            doc = self.projects_collection.find_one({"project_id": project_id, "user_id": user_id})

            if not doc:
                return []

            return [
                ProjectShare(
                    user_id=s["user_id"],
                    user_email=s["user_email"],
                    user_name=s.get("user_name"),
                    shared_by=s["shared_by"],
                    shared_at=s["shared_at"],
                )
                for s in doc.get("shares", [])
            ]
        except Exception as e:
            logger.error(f"Failed to list project shares: {e}")
            raise

    # =========================================================================
    # Project Snippet Methods
    # =========================================================================

    def get_snippets(self, project_id: str, user_id: str) -> list[Snippet]:
        """Get all snippets for a project.

        Access is allowed for both project owner and shared users.
        """
        try:
            project = self.get_project(project_id, user_id)
            if not project:
                return []

            # Convert dicts to Snippet models
            return [Snippet(**s) if isinstance(s, dict) else s for s in project.snippets]
        except Exception as e:
            logger.error(f"Failed to get snippets for project {project_id}: {e}")
            raise

    def add_snippet(self, project_id: str, user_id: str, snippet_data: SnippetCreate) -> Snippet:
        """Add a snippet to a project (owner only)."""
        try:
            # Verify caller is the owner
            doc = self.projects_collection.find_one({"project_id": project_id, "user_id": user_id})

            if not doc:
                raise ValueError("Project not found or you are not the owner")

            # Check total size limit (50KB)
            existing_snippets = doc.get("snippets", [])
            total_size = sum(len(s.get("code", "").encode("utf-8")) for s in existing_snippets)
            new_size = len(snippet_data.code.encode("utf-8"))
            if total_size + new_size > 50 * 1024:
                raise ValueError("Total snippet size exceeds 50KB limit")

            now = datetime.utcnow()
            snippet = Snippet(
                id=str(uuid.uuid4()),
                name=snippet_data.name,
                category=snippet_data.category,
                description=snippet_data.description,
                code=snippet_data.code,
                enabled=snippet_data.enabled,
                created_at=now,
                updated_at=now,
            )

            # Use $push for atomic array operation
            self.projects_collection.update_one(
                {"project_id": project_id},
                {
                    "$push": {"snippets": snippet.model_dump()},
                    "$set": {"updated_at": now},
                },
            )

            logger.info(f"Added snippet {snippet.id} to project {project_id}")
            return snippet
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to add snippet to project {project_id}: {e}")
            raise

    def update_snippet(
        self,
        project_id: str,
        user_id: str,
        snippet_id: str,
        updates: SnippetUpdate,
    ) -> Optional[Snippet]:
        """Update a snippet in a project (owner only)."""
        try:
            # Verify caller is the owner
            doc = self.projects_collection.find_one({"project_id": project_id, "user_id": user_id})

            if not doc:
                raise ValueError("Project not found or you are not the owner")

            # Find the snippet
            snippets = doc.get("snippets", [])
            snippet_index = None
            for i, s in enumerate(snippets):
                if s.get("id") == snippet_id:
                    snippet_index = i
                    break

            if snippet_index is None:
                return None

            # Check size limit if code is being updated
            if updates.code is not None:
                other_size = sum(
                    len(s.get("code", "").encode("utf-8"))
                    for i, s in enumerate(snippets)
                    if i != snippet_index
                )
                new_size = len(updates.code.encode("utf-8"))
                if other_size + new_size > 50 * 1024:
                    raise ValueError("Total snippet size would exceed 50KB limit")

            # Build update dict
            now = datetime.utcnow()
            update_fields = {"snippets.$.updated_at": now}

            if updates.name is not None:
                update_fields["snippets.$.name"] = updates.name
            if updates.category is not None:
                update_fields["snippets.$.category"] = updates.category
            if updates.description is not None:
                update_fields["snippets.$.description"] = updates.description
            if updates.code is not None:
                update_fields["snippets.$.code"] = updates.code
            if updates.enabled is not None:
                update_fields["snippets.$.enabled"] = updates.enabled

            update_fields["updated_at"] = now

            # Update using positional operator
            self.projects_collection.update_one(
                {"project_id": project_id, "snippets.id": snippet_id},
                {"$set": update_fields},
            )

            # Fetch and return updated snippet
            updated_doc = self.projects_collection.find_one({"project_id": project_id})
            if updated_doc:
                for s in updated_doc.get("snippets", []):
                    if s.get("id") == snippet_id:
                        return Snippet(**s)

            return None
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to update snippet {snippet_id} in project {project_id}: {e}")
            raise

    def delete_snippet(self, project_id: str, user_id: str, snippet_id: str) -> bool:
        """Delete a snippet from a project (owner only)."""
        try:
            # Verify caller is the owner
            doc = self.projects_collection.find_one({"project_id": project_id, "user_id": user_id})

            if not doc:
                raise ValueError("Project not found or you are not the owner")

            # Check if snippet exists before trying to delete
            snippets = doc.get("snippets", [])
            snippet_exists = any(s.get("id") == snippet_id for s in snippets)

            if not snippet_exists:
                return False

            self.projects_collection.update_one(
                {"project_id": project_id},
                {
                    "$pull": {"snippets": {"id": snippet_id}},
                    "$set": {"updated_at": datetime.utcnow()},
                },
            )

            logger.info(f"Deleted snippet {snippet_id} from project {project_id}")
            return True
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete snippet {snippet_id} from project {project_id}: {e}")
            raise

    def toggle_snippet(self, project_id: str, user_id: str, snippet_id: str) -> Optional[Snippet]:
        """Toggle a snippet's enabled status (owner only)."""
        try:
            # Verify caller is the owner and get current snippet
            doc = self.projects_collection.find_one({"project_id": project_id, "user_id": user_id})

            if not doc:
                raise ValueError("Project not found or you are not the owner")

            # Find the snippet and its current enabled state
            snippets = doc.get("snippets", [])
            current_enabled = None
            for s in snippets:
                if s.get("id") == snippet_id:
                    current_enabled = s.get("enabled", True)
                    break

            if current_enabled is None:
                return None

            # Toggle the enabled state
            new_enabled = not current_enabled
            now = datetime.utcnow()

            self.projects_collection.update_one(
                {"project_id": project_id, "snippets.id": snippet_id},
                {
                    "$set": {
                        "snippets.$.enabled": new_enabled,
                        "snippets.$.updated_at": now,
                        "updated_at": now,
                    }
                },
            )

            # Fetch and return updated snippet
            updated_doc = self.projects_collection.find_one({"project_id": project_id})
            if updated_doc:
                for s in updated_doc.get("snippets", []):
                    if s.get("id") == snippet_id:
                        return Snippet(**s)

            return None
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to toggle snippet {snippet_id} in project {project_id}: {e}")
            raise
