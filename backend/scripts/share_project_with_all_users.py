"""
Script to share a demo project with all users in the database.

This is a database-level solution that doesn't require backend/frontend changes.
The existing sharing mechanism in the app will automatically show the shared project
to all users because the query uses: {"shares.user_id": user_id}

Usage:
    uv run python scripts/share_project_with_all_users.py

Options:
    --dry-run       Preview changes without modifying the database
    --project-id    Specify a custom project ID to share (default: Project Alpha)
"""

import argparse
import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Add the backend src to path for importing settings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def get_mongodb_client() -> MongoClient:
    """Get MongoDB client from app settings or environment variable."""
    # Try to get connection string from app settings first
    try:
        from src.config.settings import get_settings

        settings = get_settings()
        connection_string = (
            settings.mongodb_uri
            or settings.mongodb_connection_string
            or os.getenv("MONGODB_URI")
            or os.getenv("MONGODB_CONNECTION_STRING")
        )
    except Exception:
        # Fallback to environment variables
        connection_string = (
            os.getenv("MONGODB_URI")
            or os.getenv("MONGODB_CONNECTION_STRING")
            or "mongodb://localhost:27017"
        )

    if not connection_string:
        raise ValueError(
            "MongoDB connection string not found. "
            "Set MONGODB_URI or MONGODB_CONNECTION_STRING environment variable."
        )

    return MongoClient(connection_string)


def find_demo_project(db, project_id: str | None = None):
    """Find the demo project to share with all users.

    If project_id is provided, use that. Otherwise, find 'Project Alpha'.
    """
    if project_id:
        project = db.projects.find_one({"project_id": project_id})
        if not project:
            print(f"❌ Project with ID '{project_id}' not found")
            return None
        return project

    # Default: Find Project Alpha
    project = db.projects.find_one({"name": "Project Alpha"})
    if project:
        return project

    # Fallback: Find any project with conversations
    project = db.projects.find_one(
        {"conversation_count": {"$gt": 0}}, sort=[("conversation_count", -1)]
    )
    return project


def get_all_users_except_owner(db, owner_id: str):
    """Get all users except the project owner."""
    return list(db.users.find({"user_id": {"$ne": owner_id}}))


def get_existing_share_user_ids(project: dict) -> set:
    """Get set of user IDs that already have access to the project."""
    shares = project.get("shares", [])
    return {share["user_id"] for share in shares}


def share_project_with_users(db, project: dict, users: list, shared_by: str, dry_run: bool = False):
    """Add share records for all users who don't already have access."""
    project_id = project["project_id"]
    project_name = project["name"]
    existing_shares = get_existing_share_user_ids(project)

    new_shares = []
    for user in users:
        user_id = user["user_id"]

        # Skip if user already has access
        if user_id in existing_shares:
            print(f"  ⏭️  Skipping {user['email']} (already has access)")
            continue

        share_record = {
            "user_id": user_id,
            "user_email": user["email"],
            "user_name": user.get("name"),
            "shared_by": shared_by,
            "shared_at": datetime.now(timezone.utc),
        }
        new_shares.append(share_record)
        print(f"  ➕ Will share with {user['email']} ({user.get('name', 'N/A')})")

    if not new_shares:
        print(f"\n✅ Project '{project_name}' is already shared with all users!")
        return 0

    if dry_run:
        print(f"\n🔍 DRY RUN: Would add {len(new_shares)} new shares to '{project_name}'")
        return len(new_shares)

    # Update the project with new shares
    try:
        result = db.projects.update_one(
            {"project_id": project_id}, {"$push": {"shares": {"$each": new_shares}}}
        )

        if result.modified_count > 0:
            print(f"\n✅ Successfully shared '{project_name}' with {len(new_shares)} users!")
            return len(new_shares)
        else:
            print(f"\n⚠️  No changes made to project '{project_name}'")
            return 0

    except PyMongoError as e:
        print(f"\n❌ Failed to update project: {e}")
        return -1


def main():
    parser = argparse.ArgumentParser(
        description="Share a demo project with all users in the database"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without modifying the database"
    )
    parser.add_argument(
        "--project-id",
        type=str,
        help="Specific project ID to share (default: auto-detect 'Project Alpha')",
    )
    args = parser.parse_args()

    print("🚀 Share Demo Project Script")
    print("=" * 50)

    # Connect to MongoDB
    try:
        client = get_mongodb_client()
        db = client.genome_chat
        print(f"✅ Connected to MongoDB")
    except PyMongoError as e:
        print(f"❌ Failed to connect to MongoDB: {e}")
        return 1

    # Find the demo project
    project = find_demo_project(db, args.project_id)
    if not project:
        print("❌ No suitable demo project found")
        return 1

    owner_id = project["user_id"]
    project_name = project["name"]
    project_id = project["project_id"]
    conversation_count = project.get("conversation_count", 0)

    print(f"\n📁 Demo Project: '{project_name}'")
    print(f"   ID: {project_id}")
    print(f"   Owner: {owner_id}")
    print(f"   Conversations: {conversation_count}")
    print(f"   Current shares: {len(project.get('shares', []))}")

    # Get all users except owner
    users = get_all_users_except_owner(db, owner_id)
    print(f"\n👥 Total users in system: {len(users) + 1}")
    print(f"   Users to potentially share with: {len(users)}")

    if not users:
        print("\n⚠️  No other users found in the database")
        return 0

    print("\n📝 Processing users:")
    result = share_project_with_users(db, project, users, owner_id, args.dry_run)

    if result >= 0:
        print("\n" + "=" * 50)
        if args.dry_run:
            print("🔍 DRY RUN COMPLETE - No changes were made")
            print("   Run without --dry-run to apply changes")
        else:
            print("✅ COMPLETE - New users will now see the demo project!")
        return 0

    return 1


if __name__ == "__main__":
    exit(main())
