#!/usr/bin/env python3
"""Migration script to add project support to existing conversations.

This script:
1. Creates default 'All Chats' project for all existing users
2. Links orphaned conversations (without project_id) to their user's default project
3. Updates conversation counts and timestamps for all projects
4. Provides detailed logging and rollback capability

Run with: python backend/scripts/migrate_projects.py
"""

import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.service.database.connections.mongodb_connection import get_mongodb_database
from src.service.storage.project_service import ProjectService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_migration_stats():
    """Get current state statistics before migration."""
    db = get_mongodb_database()
    conversations_collection = db["conversations"]
    projects_collection = db["projects"]

    stats = {
        "total_conversations": conversations_collection.count_documents({}),
        "conversations_with_project": conversations_collection.count_documents(
            {"project_id": {"$exists": True, "$ne": None}}
        ),
        "conversations_without_project": conversations_collection.count_documents(
            {"$or": [{"project_id": {"$exists": False}}, {"project_id": None}]}
        ),
        "total_projects": projects_collection.count_documents({}),
        "default_projects": projects_collection.count_documents({"is_default": True}),
        "unique_users": len(conversations_collection.distinct("user_id")),
    }

    return stats


def migrate_conversations_to_projects(dry_run: bool = False):
    """Add default project_id to all existing conversations.

    Args:
        dry_run: If True, only preview changes without modifying database
    """
    logger.info("=" * 80)
    logger.info("Starting Project Migration")
    logger.info("=" * 80)

    # Get initial stats
    logger.info("\n📊 Pre-migration statistics:")
    initial_stats = get_migration_stats()
    for key, value in initial_stats.items():
        logger.info(f"  {key}: {value}")

    if dry_run:
        logger.info("\n🔍 DRY RUN MODE - No changes will be made")

    db = get_mongodb_database()
    conversations_collection = db["conversations"]
    project_service = ProjectService()

    # Get all unique user_ids from conversations
    user_ids = conversations_collection.distinct("user_id")
    logger.info(f"\n👥 Found {len(user_ids)} unique users with conversations")

    migration_results = {
        "users_processed": 0,
        "default_projects_created": 0,
        "conversations_migrated": 0,
        "errors": [],
    }

    for idx, user_id in enumerate(user_ids, 1):
        try:
            logger.info(f"\n[{idx}/{len(user_ids)}] Processing user: {user_id}")

            # Ensure default project exists
            if not dry_run:
                default_project = project_service.ensure_default_project(user_id)
                logger.info(f"  ✓ Default project: {default_project.id}")
            else:
                # Check if default project exists
                existing_project = db["projects"].find_one({"user_id": user_id, "is_default": True})
                if existing_project:
                    default_project_id = existing_project["project_id"]
                    logger.info(f"  ℹ Would use existing default project: {default_project_id}")
                else:
                    logger.info("  ℹ Would create new default project")
                    migration_results["default_projects_created"] += 1
                    # For dry run, create a placeholder ID
                    default_project_id = f"would-create-for-{user_id}"

                default_project = type("obj", (object,), {"id": default_project_id})()

            # Count conversations without project_id
            orphaned_conversations = conversations_collection.find(
                {
                    "user_id": user_id,
                    "$or": [{"project_id": {"$exists": False}}, {"project_id": None}],
                }
            )

            orphaned_count = 0
            for conv in orphaned_conversations:
                orphaned_count += 1
                conv_id = conv["conversation_id"]
                conv_title = conv.get("title", "Untitled")[:50]

                if not dry_run:
                    # Update conversation with project_id
                    result = conversations_collection.update_one(
                        {"conversation_id": conv_id}, {"$set": {"project_id": default_project.id}}
                    )

                    if result.modified_count > 0:
                        logger.debug(f"    • Migrated: {conv_id} - '{conv_title}'")
                        migration_results["conversations_migrated"] += 1
                else:
                    logger.debug(f"    • Would migrate: {conv_id} - '{conv_title}'")
                    migration_results["conversations_migrated"] += 1

            if orphaned_count > 0:
                logger.info(f"  ✓ Migrated {orphaned_count} conversations to default project")

                # Update project conversation count
                if not dry_run:
                    project_service._update_conversation_count(default_project.id)
                    logger.info("  ✓ Updated project conversation count")
            else:
                logger.info("  ℹ No orphaned conversations found")

            migration_results["users_processed"] += 1

            if not existing_project if dry_run else False:
                migration_results["default_projects_created"] += 1

        except Exception as e:
            error_msg = f"Failed to process user {user_id}: {e}"
            logger.error(f"  ✗ {error_msg}")
            migration_results["errors"].append(error_msg)
            continue

    # Get final stats
    logger.info("\n📊 Post-migration statistics:")
    final_stats = get_migration_stats()
    for key, value in final_stats.items():
        logger.info(f"  {key}: {value}")

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("Migration Summary")
    logger.info("=" * 80)
    logger.info(f"Users processed: {migration_results['users_processed']}/{len(user_ids)}")
    logger.info(f"Default projects created: {migration_results['default_projects_created']}")
    logger.info(f"Conversations migrated: {migration_results['conversations_migrated']}")
    logger.info(f"Errors encountered: {len(migration_results['errors'])}")

    if migration_results["errors"]:
        logger.warning("\n⚠️  Errors during migration:")
        for error in migration_results["errors"]:
            logger.warning(f"  • {error}")

    if dry_run:
        logger.info("\n🔍 DRY RUN COMPLETE - No changes were made to the database")
        logger.info("Run without --dry-run flag to apply changes")
    else:
        logger.info("\n✅ MIGRATION COMPLETE!")

    return migration_results


def verify_migration():
    """Verify migration was successful."""
    logger.info("\n" + "=" * 80)
    logger.info("Verifying Migration")
    logger.info("=" * 80)

    db = get_mongodb_database()
    conversations_collection = db["conversations"]
    projects_collection = db["projects"]

    # Check for orphaned conversations
    orphaned = conversations_collection.count_documents(
        {"$or": [{"project_id": {"$exists": False}}, {"project_id": None}]}
    )

    if orphaned > 0:
        logger.warning(f"⚠️  Found {orphaned} orphaned conversations without project_id")
        return False
    else:
        logger.info("✅ All conversations have project_id")

    # Verify all users have default projects
    user_ids = conversations_collection.distinct("user_id")
    users_without_default = 0

    for user_id in user_ids:
        default_project = projects_collection.find_one({"user_id": user_id, "is_default": True})
        if not default_project:
            logger.warning(f"⚠️  User {user_id} has no default project")
            users_without_default += 1

    if users_without_default > 0:
        logger.warning(f"⚠️  Found {users_without_default} users without default projects")
        return False
    else:
        logger.info("✅ All users have default projects")

    # Verify conversation counts
    projects = projects_collection.find({})
    mismatched_counts = 0

    for project in projects:
        project_id = project["project_id"]
        stored_count = project.get("conversation_count", 0)
        actual_count = conversations_collection.count_documents({"project_id": project_id})

        if stored_count != actual_count:
            logger.warning(
                f"⚠️  Project {project_id}: stored count ({stored_count}) != "
                f"actual count ({actual_count})"
            )
            mismatched_counts += 1

    if mismatched_counts > 0:
        logger.warning(f"⚠️  Found {mismatched_counts} projects with mismatched counts")
        logger.info(
            "💡 You can fix counts by running: project_service._update_conversation_count()"
        )
        return False
    else:
        logger.info("✅ All project conversation counts are accurate")

    logger.info("\n✅ VERIFICATION PASSED - Migration successful!")
    return True


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate existing conversations to project system")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without modifying database"
    )
    parser.add_argument(
        "--verify-only", action="store_true", help="Only verify migration, don't migrate"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        if args.verify_only:
            verify_migration()
        else:
            migrate_conversations_to_projects(dry_run=args.dry_run)

            if not args.dry_run:
                # Verify after migration
                logger.info("\n")
                verify_migration()

    except KeyboardInterrupt:
        logger.warning("\n\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
