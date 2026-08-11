"""User authentication and management service with MongoDB."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from pymongo.errors import DuplicateKeyError

from src.models.user import User, UserCreate, UserInDB, UserSummary
from src.service.auth.password import hash_password
from src.service.database.connections.mongodb_connection import get_mongodb_database

logger = logging.getLogger(__name__)


class UserService:
    """Service class for user CRUD operations with MongoDB."""

    def __init__(self, db_name: Optional[str] = None):
        """Initialize UserService with MongoDB database.

        Args:
            db_name: MongoDB database name (defaults to settings.mongodb_db_name)
        """
        self.db = get_mongodb_database(db_name)
        self.users_collection = self.db["users"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create indexes on users collection."""
        try:
            # Create unique index on user_id
            self.users_collection.create_index("user_id", unique=True)
            # Create unique index on email
            self.users_collection.create_index("email", unique=True)
            logger.debug("User collection indexes created/verified")
        except Exception as e:
            logger.warning(f"Failed to create user indexes: {e}")

    def create_user(self, user_data: UserCreate) -> User:
        """Create a new user in the database.

        Args:
            user_data: User creation data with email, name, and password

        Returns:
            Created user object (without password)

        Raises:
            ValueError: If email already exists
            Exception: If database operation fails

        Example:
            >>> service = UserService()
            >>> user = service.create_user(UserCreate(
            ...     email="test@example.com",
            ...     name="Test User",
            ...     password="password123"
            ... ))
        """
        try:
            # Check if email already exists
            existing_user = self.users_collection.find_one({"email": user_data.email})
            if existing_user:
                raise ValueError("Email already registered")

            # Generate user ID and hash password
            user_id = str(uuid.uuid4())
            hashed_password = hash_password(user_data.password)
            now = datetime.now(timezone.utc)

            # Insert user
            user_doc = {
                "user_id": user_id,
                "email": user_data.email,
                "name": user_data.name,
                "hashed_password": hashed_password,
                "role": "user",
                "created_at": now,
                "updated_at": now,
            }

            self.users_collection.insert_one(user_doc)

            logger.info(f"Created user: {user_data.email}")

            # Return user without password
            return User(
                id=user_id,
                email=user_data.email,
                name=user_data.name,
                role="user",
                created_at=now,
            )

        except DuplicateKeyError as e:
            logger.error(f"Duplicate key error creating user: {e}")
            raise ValueError("Email already registered") from e
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise

    def get_user_by_email(self, email: str) -> Optional[UserInDB]:
        """Get user by email address.

        Args:
            email: User's email address

        Returns:
            UserInDB object with hashed password, or None if not found

        Example:
            >>> service = UserService()
            >>> user = service.get_user_by_email("test@example.com")
        """
        try:
            user_doc = self.users_collection.find_one({"email": email})
            if user_doc is None:
                return None

            return UserInDB(
                id=user_doc["user_id"],
                email=user_doc["email"],
                name=user_doc["name"],
                hashed_password=user_doc["hashed_password"],
                role=user_doc.get("role", "user"),
                created_at=user_doc["created_at"],
            )

        except Exception as e:
            logger.error(f"Failed to get user by email: {e}")
            raise

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID.

        Args:
            user_id: User's unique identifier

        Returns:
            User object (without password), or None if not found

        Example:
            >>> service = UserService()
            >>> user = service.get_user_by_id("user-123")
        """
        try:
            user_doc = self.users_collection.find_one({"user_id": user_id})
            if user_doc is None:
                return None

            return User(
                id=user_doc["user_id"],
                email=user_doc["email"],
                name=user_doc["name"],
                role=user_doc.get("role", "user"),
                created_at=user_doc["created_at"],
            )

        except Exception as e:
            logger.error(f"Failed to get user by ID: {e}")
            raise

    def update_user(
        self, user_id: str, name: Optional[str] = None, email: Optional[str] = None
    ) -> Optional[User]:
        """Update user profile information.

        Args:
            user_id: User's unique identifier
            name: New name (optional)
            email: New email (optional)

        Returns:
            Updated user object, or None if not found

        Raises:
            ValueError: If email already exists (when updating email)
        """
        try:
            update_data = {"updated_at": datetime.now(timezone.utc)}
            if name is not None:
                update_data["name"] = name
            if email is not None:
                # Check if email already exists
                existing_user = self.users_collection.find_one(
                    {"email": email, "user_id": {"$ne": user_id}}
                )
                if existing_user:
                    raise ValueError("Email already registered")
                update_data["email"] = email

            result = self.users_collection.update_one({"user_id": user_id}, {"$set": update_data})

            if result.modified_count == 0:
                return None

            return self.get_user_by_id(user_id)

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            raise

    def delete_user(self, user_id: str) -> bool:
        """Delete a user from the database.

        Args:
            user_id: User's unique identifier

        Returns:
            True if deleted, False if not found
        """
        try:
            result = self.users_collection.delete_one({"user_id": user_id})
            if result.deleted_count > 0:
                logger.info(f"Deleted user: {user_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to delete user: {e}")
            raise

    def search_users(self, query: str, exclude_user_id: str, limit: int = 10) -> list[UserSummary]:
        """Search users by email or name for sharing UI.

        Args:
            query: Search string (partial email or name, min 2 chars)
            exclude_user_id: User ID to exclude from results (current user)
            limit: Maximum number of results to return

        Returns:
            List of UserSummary objects matching the query
        """
        try:
            if len(query) < 2:
                return []

            # Case-insensitive partial match on email or name
            cursor = self.users_collection.find(
                {
                    "user_id": {"$ne": exclude_user_id},
                    "$or": [
                        {"email": {"$regex": query, "$options": "i"}},
                        {"name": {"$regex": query, "$options": "i"}},
                    ],
                },
                {"user_id": 1, "email": 1, "name": 1},  # Project only needed fields
            ).limit(limit)

            return [
                UserSummary(
                    id=doc["user_id"],
                    email=doc["email"],
                    name=doc["name"],
                )
                for doc in cursor
            ]
        except Exception as e:
            logger.error(f"Failed to search users: {e}")
            raise
