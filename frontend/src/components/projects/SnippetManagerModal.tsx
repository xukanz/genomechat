/**
 * SnippetManagerModal - Modal wrapper for managing project code snippets
 */

import type { Project } from '../../types/project'
import { SnippetManager } from './SnippetManager'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Code } from 'lucide-react'

interface SnippetManagerModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  project: Project
}

export function SnippetManagerModal({
  open,
  onOpenChange,
  project,
}: SnippetManagerModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Code className="h-5 w-5" />
            Code Snippets
          </DialogTitle>
          <DialogDescription>
            Manage code snippets for "{project.name}". Enabled snippets are automatically
            injected into the Coder Agent's prompt as reference patterns.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-hidden">
          <SnippetManager project={project} />
        </div>
      </DialogContent>
    </Dialog>
  )
}
