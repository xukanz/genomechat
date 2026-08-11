"""Project management API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.models.project import (
    Project,
    ProjectCreate,
    ProjectList,
    ProjectShare,
    ProjectShareCreate,
    ProjectShareList,
    ProjectUpdate,
)
from src.models.snippet import Snippet, SnippetCreate, SnippetList, SnippetUpdate
from src.models.user import User, UserSummary
from src.service.auth.dependencies import get_current_user
from src.service.auth.user_service import UserService
from src.service.storage.project_service import ProjectService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectList)
async def list_projects(
    current_user: User = Depends(get_current_user),
) -> ProjectList:
    """List all projects for the current user."""
    try:
        project_service = ProjectService()

        # Ensure default project exists
        project_service.ensure_default_project(current_user.id)

        projects = project_service.list_user_projects(current_user.id)
        return ProjectList(projects=projects, count=len(projects))

    except Exception as e:
        logger.error(f"Failed to list projects for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list projects",
        ) from e


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(get_current_user),
) -> Project:
    """Create a new project."""
    try:
        project_service = ProjectService()
        project = project_service.create_project(current_user.id, project_data)
        return project

    except Exception as e:
        logger.error(f"Failed to create project for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create project",
        ) from e


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> Project:
    """Get a specific project by ID."""
    try:
        project_service = ProjectService()
        project = project_service.get_project(project_id, current_user.id)

        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )

        return project

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get project {project_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get project",
        ) from e


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    updates: ProjectUpdate,
    current_user: User = Depends(get_current_user),
) -> Project:
    """Update project metadata."""
    try:
        project_service = ProjectService()

        success = project_service.update_project(project_id, current_user.id, updates)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or no changes made",
            )

        # Return updated project
        project = project_service.get_project(project_id, current_user.id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )

        return project

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to update project {project_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update project",
        ) from e


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a project (moves conversations to default project)."""
    try:
        project_service = ProjectService()

        success = project_service.delete_project(project_id, current_user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or cannot delete default project",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to delete project {project_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete project",
        ) from e


@router.post(
    "/{project_id}/conversations/{conversation_id}/move",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def move_conversation(
    project_id: str,
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Move a conversation to this project."""
    try:
        project_service = ProjectService()

        success = project_service.move_conversation_to_project(
            conversation_id, project_id, current_user.id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project or conversation not found",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to move conversation {conversation_id} to project {project_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to move conversation",
        ) from e


# =============================================================================
# Project Sharing Endpoints
# =============================================================================


@router.get("/{project_id}/shares", response_model=ProjectShareList)
async def list_project_shares(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> ProjectShareList:
    """List all users a project is shared with (owner only)."""
    try:
        project_service = ProjectService()
        shares = project_service.list_project_shares(project_id, current_user.id)
        return ProjectShareList(shares=shares, count=len(shares))

    except Exception as e:
        logger.error(f"Failed to list shares for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list project shares",
        ) from e


@router.post(
    "/{project_id}/shares", response_model=ProjectShare, status_code=status.HTTP_201_CREATED
)
async def share_project(
    project_id: str,
    share_data: ProjectShareCreate,
    current_user: User = Depends(get_current_user),
) -> ProjectShare:
    """Share a project with another user (owner only)."""
    try:
        project_service = ProjectService()
        user_service = UserService()

        # Get target user info for denormalization
        target_user = user_service.get_user_by_id(share_data.user_id)
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user_info = UserSummary(
            id=target_user.id,
            email=target_user.email,
            name=target_user.name,
        )

        share = project_service.share_project(
            project_id, current_user.id, share_data.user_id, user_info
        )
        return share

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to share project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to share project",
        ) from e


@router.delete("/{project_id}/shares/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_share(
    project_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Remove a user's access to a shared project (owner only)."""
    try:
        project_service = ProjectService()

        success = project_service.remove_share(project_id, current_user.id, user_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Share not found",
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove share from project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove share",
        ) from e


# =============================================================================
# Project Snippet Endpoints
# =============================================================================


@router.get("/{project_id}/snippets", response_model=SnippetList)
async def list_snippets(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> SnippetList:
    """List all snippets for a project.

    Access is allowed for both project owner and shared users.
    """
    try:
        project_service = ProjectService()
        snippets = project_service.get_snippets(project_id, current_user.id)
        return SnippetList(snippets=snippets, count=len(snippets))

    except Exception as e:
        logger.error(f"Failed to list snippets for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list snippets",
        ) from e


@router.post("/{project_id}/snippets", response_model=Snippet, status_code=status.HTTP_201_CREATED)
async def create_snippet(
    project_id: str,
    snippet_data: SnippetCreate,
    current_user: User = Depends(get_current_user),
) -> Snippet:
    """Create a new snippet in a project (owner only)."""
    try:
        project_service = ProjectService()
        snippet = project_service.add_snippet(project_id, current_user.id, snippet_data)
        return snippet

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Failed to create snippet in project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create snippet",
        ) from e


@router.put("/{project_id}/snippets/{snippet_id}", response_model=Snippet)
async def update_snippet(
    project_id: str,
    snippet_id: str,
    updates: SnippetUpdate,
    current_user: User = Depends(get_current_user),
) -> Snippet:
    """Update a snippet in a project (owner only)."""
    try:
        project_service = ProjectService()
        snippet = project_service.update_snippet(project_id, current_user.id, snippet_id, updates)

        if snippet is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Snippet not found",
            )

        return snippet

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to update snippet {snippet_id} in project {project_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update snippet",
        ) from e


@router.delete("/{project_id}/snippets/{snippet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_snippet(
    project_id: str,
    snippet_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a snippet from a project (owner only)."""
    try:
        project_service = ProjectService()
        success = project_service.delete_snippet(project_id, current_user.id, snippet_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Snippet not found",
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to delete snippet {snippet_id} from project {project_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete snippet",
        ) from e


@router.patch("/{project_id}/snippets/{snippet_id}/toggle", response_model=Snippet)
async def toggle_snippet(
    project_id: str,
    snippet_id: str,
    current_user: User = Depends(get_current_user),
) -> Snippet:
    """Toggle a snippet's enabled status (owner only)."""
    try:
        project_service = ProjectService()
        snippet = project_service.toggle_snippet(project_id, current_user.id, snippet_id)

        if snippet is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Snippet not found",
            )

        return snippet

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to toggle snippet {snippet_id} in project {project_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to toggle snippet",
        ) from e
