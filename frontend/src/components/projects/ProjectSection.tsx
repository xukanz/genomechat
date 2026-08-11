/**
 * ProjectSection - Main container for project management in sidebar
 * Displays collapsible list of projects with create button
 */

import { useEffect, useState } from 'react'
import { Plus, ChevronDown, ChevronRight } from 'lucide-react'
import { useProjectStore } from '../../store/projectStore'
import { useConversationStore } from '../../store/conversationStore'
import { ProjectItem } from './ProjectItem'
import { CreateProjectDialog } from './CreateProjectDialog'
import { Button } from '../ui/button'
import { cn } from '../../lib/utils'

export function ProjectSection() {
  const [isExpanded, setIsExpanded] = useState(true)
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)

  const { projects, selectedProjectId, isLoading, loadProjects, setSelectedProject } =
    useProjectStore()
  const { loadConversations } = useConversationStore()

  // Load projects on mount
  useEffect(() => {
    loadProjects()
  }, [loadProjects])

  // Load conversations when selected project changes
  useEffect(() => {
    if (selectedProjectId) {
      loadConversations(selectedProjectId)
    }
  }, [selectedProjectId, loadConversations])

  const handleProjectSelect = (projectId: string) => {
    setSelectedProject(projectId)
  }

  const handleCreateProject = () => {
    setIsCreateDialogOpen(true)
  }

  return (
    <div className="border-b border-border">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 hover:bg-accent/50 transition-colors">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 flex-1 text-sm font-medium text-foreground"
        >
          {isExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
          <span>Projects</span>
          {!isLoading && projects.length > 0 && (
            <span className="text-xs text-muted-foreground">({projects.length})</span>
          )}
        </button>

        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={handleCreateProject}
          title="Create new project"
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      {/* Project List */}
      {isExpanded && (
        <div className={cn('space-y-0.5 pb-2', isLoading && 'opacity-50')}>
          {isLoading && projects.length === 0 ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">Loading projects...</div>
          ) : projects.length === 0 ? (
            <div className="px-3 py-2 text-xs text-muted-foreground">
              No projects yet. Create one to organize your chats.
            </div>
          ) : (
            <>
              {/* Default project first */}
              {projects
                .filter((p) => p.is_default)
                .map((project) => (
                  <ProjectItem
                    key={project.id}
                    project={project}
                    isSelected={selectedProjectId === project.id}
                    onSelect={handleProjectSelect}
                  />
                ))}

              {/* Other projects */}
              {projects
                .filter((p) => !p.is_default)
                .map((project) => (
                  <ProjectItem
                    key={project.id}
                    project={project}
                    isSelected={selectedProjectId === project.id}
                    onSelect={handleProjectSelect}
                  />
                ))}
            </>
          )}
        </div>
      )}

      {/* Create Project Dialog */}
      <CreateProjectDialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen} />
    </div>
  )
}
