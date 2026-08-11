/**
 * ProjectItem - Single project row with color indicator and count badge
 */

import { MessageSquare, Users } from 'lucide-react'
import type { Project } from '../../types/project'
import { cn } from '../../lib/utils'
import { ProjectDropdown } from './ProjectDropdown'

interface ProjectItemProps {
  project: Project
  isSelected: boolean
  onSelect: (projectId: string) => void
}

export function ProjectItem({ project, isSelected, onSelect }: ProjectItemProps) {
  const handleClick = () => {
    onSelect(project.id)
  }

  return (
    <div
      className={cn(
        'group relative flex items-start gap-2 px-3 py-2 cursor-pointer transition-colors',
        'hover:bg-accent/50',
        isSelected && 'bg-accent'
      )}
      onClick={handleClick}
    >
      {/* Color Indicator */}
      <div
        className="w-2 h-2 rounded-full flex-shrink-0 mt-1"
        style={{ backgroundColor: project.color || '#6B7280' }}
      />

      {/* Project Name - takes remaining space but reserves room for badge */}
      <div className="flex-1 min-w-0 pr-16">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium text-foreground truncate">{project.name}</span>
          {/* Shared with you indicator */}
          {project.is_shared && (
            <span
              className="flex items-center text-xs text-muted-foreground"
              title="Shared with you"
            >
              <Users className="h-3 w-3" />
            </span>
          )}
          {/* You've shared this project indicator */}
          {project.is_owner && project.shares.length > 0 && (
            <span
              className="flex items-center gap-0.5 text-xs text-muted-foreground"
              title={`Shared with ${project.shares.length} user${project.shares.length !== 1 ? 's' : ''}`}
            >
              <Users className="h-3 w-3" />
              <span>{project.shares.length}</span>
            </span>
          )}
        </div>
        {project.description && (
          <div className="text-xs text-muted-foreground truncate">{project.description}</div>
        )}
      </div>

      {/* Conversation Count Badge - absolutely positioned to the right */}
      <div
        className={cn(
          'absolute right-3 top-2 flex items-center justify-center min-w-[44px] h-6 px-2.5 rounded-full text-xs font-medium',
          'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300'
        )}
      >
        <MessageSquare className="h-3 w-3 mr-1" />
        <span>{project.conversation_count || 0}</span>
      </div>

      {/* Dropdown Menu (hidden on default project) - positioned over the badge area */}
      {!project.is_default && (
        <div className="absolute right-14 top-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
          <ProjectDropdown project={project} />
        </div>
      )}
    </div>
  )
}
