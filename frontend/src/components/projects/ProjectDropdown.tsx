/**
 * ProjectDropdown - Context menu for project actions (rename, delete, change color, snippets)
 */

import { useState } from 'react'
import { MoreHorizontal, Edit2, Trash2, Palette, Users, Code } from 'lucide-react'
import type { Project } from '../../types/project'
import { useProjectStore } from '../../store/projectStore'
import { ShareProjectModal } from './ShareProjectModal'
import { SnippetManagerModal } from './SnippetManagerModal'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/alert-dialog'
import { Button } from '../ui/button'
import { CreateProjectDialog } from './CreateProjectDialog'

interface ProjectDropdownProps {
  project: Project
}

export function ProjectDropdown({ project }: ProjectDropdownProps) {
  const { deleteProject } = useProjectStore()
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false)
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
  const [isShareDialogOpen, setIsShareDialogOpen] = useState(false)
  const [isSnippetsDialogOpen, setIsSnippetsDialogOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  // Only owner can share, and cannot share default project
  const canShare = project.is_owner && !project.is_default

  const handleSnippets = (e: Event) => {
    e.preventDefault()
    e.stopPropagation()
    setIsSnippetsDialogOpen(true)
  }

  const handleEdit = (e: Event) => {
    e.preventDefault()
    e.stopPropagation()
    setIsEditDialogOpen(true)
  }

  const handleShare = (e: Event) => {
    e.preventDefault()
    e.stopPropagation()
    setIsShareDialogOpen(true)
  }

  const handleDelete = (e: Event) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDeleteDialogOpen(true)
  }

  const confirmDelete = async () => {
    setIsDeleting(true)
    try {
      await deleteProject(project.id)
      setIsDeleteDialogOpen(false)
    } catch (error) {
      console.error('Failed to delete project:', error)
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
          <Button variant="ghost" size="icon" className="h-6 w-6">
            <MoreHorizontal className="h-4 w-4" />
            <span className="sr-only">Project options</span>
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
          <DropdownMenuItem onSelect={handleEdit}>
            <Edit2 className="mr-2 h-4 w-4" />
            <span>Rename</span>
          </DropdownMenuItem>

          <DropdownMenuItem onSelect={handleEdit}>
            <Palette className="mr-2 h-4 w-4" />
            <span>Change Color</span>
          </DropdownMenuItem>

          {canShare && (
            <DropdownMenuItem onSelect={handleShare}>
              <Users className="mr-2 h-4 w-4" />
              <span>Share</span>
            </DropdownMenuItem>
          )}

          <DropdownMenuItem onSelect={handleSnippets}>
            <Code className="mr-2 h-4 w-4" />
            <span>Code Snippets</span>
          </DropdownMenuItem>

          <DropdownMenuSeparator />

          <DropdownMenuItem onSelect={handleDelete} className="text-destructive">
            <Trash2 className="mr-2 h-4 w-4" />
            <span>Delete Project</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Edit Dialog */}
      <CreateProjectDialog
        open={isEditDialogOpen}
        onOpenChange={setIsEditDialogOpen}
        editProject={{
          id: project.id,
          name: project.name,
          description: project.description || undefined,
          color: project.color || undefined,
        }}
      />

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent onClick={(e: React.MouseEvent) => e.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Project?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete <strong>{project.name}</strong>?
              {project.conversation_count > 0 && (
                <>
                  <br />
                  <br />
                  The {project.conversation_count} conversation
                  {project.conversation_count !== 1 && 's'} in this project will be moved to "All
                  Chats".
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Share Dialog */}
      <ShareProjectModal
        open={isShareDialogOpen}
        onOpenChange={setIsShareDialogOpen}
        project={project}
      />

      {/* Snippets Dialog */}
      <SnippetManagerModal
        open={isSnippetsDialogOpen}
        onOpenChange={setIsSnippetsDialogOpen}
        project={project}
      />
    </>
  )
}
