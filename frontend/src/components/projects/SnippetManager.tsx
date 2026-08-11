/**
 * SnippetManager - Main component for managing project code snippets
 */

import { useEffect, useState, useCallback } from 'react'
import { Code, Plus, Loader2 } from 'lucide-react'
import type { Project, Snippet, SnippetCreate, SnippetUpdate } from '../../types/project'
import { useSnippetStore } from '../../store/snippetStore'
import { SnippetCard } from './SnippetCard'
import { SnippetForm } from './SnippetForm'
import { Button } from '../ui/button'

interface SnippetManagerProps {
  project: Project
}

type ViewMode = 'list' | 'create' | 'edit'

export function SnippetManager({ project }: SnippetManagerProps) {
  const {
    snippets,
    isLoading,
    error,
    loadSnippets,
    createSnippet,
    updateSnippet,
    deleteSnippet,
    toggleSnippet,
    clearError,
  } = useSnippetStore()

  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [editingSnippet, setEditingSnippet] = useState<Snippet | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Load snippets when project changes
  useEffect(() => {
    loadSnippets(project.id)
  }, [project.id, loadSnippets])

  const handleCreate = useCallback(async (data: SnippetCreate | SnippetUpdate) => {
    setIsSubmitting(true)
    try {
      await createSnippet(project.id, data as SnippetCreate)
      setViewMode('list')
    } catch (err) {
      console.error('Failed to create snippet:', err)
    } finally {
      setIsSubmitting(false)
    }
  }, [project.id, createSnippet])

  const handleUpdate = useCallback(async (data: SnippetCreate | SnippetUpdate) => {
    if (!editingSnippet) return

    setIsSubmitting(true)
    try {
      await updateSnippet(project.id, editingSnippet.id, data as SnippetUpdate)
      setViewMode('list')
      setEditingSnippet(null)
    } catch (err) {
      console.error('Failed to update snippet:', err)
    } finally {
      setIsSubmitting(false)
    }
  }, [project.id, editingSnippet, updateSnippet])

  const handleDelete = useCallback(async (snippetId: string) => {
    try {
      await deleteSnippet(project.id, snippetId)
    } catch (err) {
      console.error('Failed to delete snippet:', err)
    }
  }, [project.id, deleteSnippet])

  const handleToggle = useCallback(async (snippetId: string) => {
    try {
      await toggleSnippet(project.id, snippetId)
    } catch (err) {
      console.error('Failed to toggle snippet:', err)
    }
  }, [project.id, toggleSnippet])

  const handleEdit = useCallback((snippet: Snippet) => {
    setEditingSnippet(snippet)
    setViewMode('edit')
  }, [])

  const handleCancel = useCallback(() => {
    setViewMode('list')
    setEditingSnippet(null)
    clearError()
  }, [clearError])

  // Render loading state
  if (isLoading && snippets.length === 0) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  // Render form view (create or edit)
  if (viewMode === 'create' || viewMode === 'edit') {
    return (
      <div className="flex flex-col h-full max-h-[60vh]">
        <div className="flex items-center gap-2 pb-4 flex-shrink-0">
          <Code className="h-5 w-5 text-muted-foreground" />
          <h3 className="font-medium">
            {viewMode === 'create' ? 'New Snippet' : 'Edit Snippet'}
          </h3>
        </div>

        {error && (
          <div className="bg-destructive/10 text-destructive px-4 py-2 rounded-md text-sm flex-shrink-0 mb-4">
            {error}
          </div>
        )}

        <div className="flex-1 overflow-y-auto pr-2">
          <SnippetForm
            snippet={editingSnippet}
            onSubmit={viewMode === 'create' ? handleCreate : handleUpdate}
            onCancel={handleCancel}
            isSubmitting={isSubmitting}
          />
        </div>
      </div>
    )
  }

  // Render list view
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Code className="h-5 w-5 text-muted-foreground" />
          <h3 className="font-medium">Code Snippets</h3>
          <span className="text-sm text-muted-foreground">
            ({snippets.length})
          </span>
        </div>
        {project.is_owner && (
          <Button
            size="sm"
            onClick={() => setViewMode('create')}
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Snippet
          </Button>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-destructive/10 text-destructive px-4 py-2 rounded-md text-sm">
          {error}
        </div>
      )}

      {/* Empty State */}
      {snippets.length === 0 ? (
        <div className="text-center py-8">
          <Code className="h-12 w-12 mx-auto text-muted-foreground/50" />
          <h4 className="mt-4 font-medium">No snippets yet</h4>
          <p className="mt-2 text-sm text-muted-foreground max-w-sm mx-auto">
            Add code snippets to this project. Enabled snippets will be automatically
            injected into the Coder Agent's prompt as reference patterns.
          </p>
          {project.is_owner && (
            <Button
              className="mt-4"
              onClick={() => setViewMode('create')}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Your First Snippet
            </Button>
          )}
        </div>
      ) : (
        <div className="h-[400px] overflow-y-auto pr-4">
          <div className="space-y-3">
            {snippets.map((snippet) => (
              <SnippetCard
                key={snippet.id}
                snippet={snippet}
                onEdit={handleEdit}
                onDelete={handleDelete}
                onToggle={handleToggle}
                isLoading={isLoading}
              />
            ))}
          </div>
        </div>
      )}

      {/* Info Footer */}
      <p className="text-xs text-muted-foreground text-center pt-2">
        Enabled snippets are injected into the Coder Agent prompt as reference patterns.
      </p>
    </div>
  )
}
