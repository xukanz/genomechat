/**
 * CreateProjectDialog - Modal for creating/editing projects
 */

import { useState } from 'react'
import { useProjectStore } from '../../store/projectStore'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Textarea } from '../ui/textarea'
import { ProjectColorPicker } from './ProjectColorPicker'

interface CreateProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editProject?: { id: string; name: string; description?: string; color?: string }
}

export function CreateProjectDialog({ open, onOpenChange, editProject }: CreateProjectDialogProps) {
  const { createProject, updateProject } = useProjectStore()

  const [name, setName] = useState(editProject?.name || '')
  const [description, setDescription] = useState(editProject?.description || '')
  const [color, setColor] = useState(editProject?.color || '#3B82F6')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!name.trim()) {
      setError('Project name is required')
      return
    }

    if (name.length > 100) {
      setError('Project name must be 100 characters or less')
      return
    }

    if (description && description.length > 500) {
      setError('Description must be 500 characters or less')
      return
    }

    setIsSubmitting(true)

    try {
      if (editProject) {
        await updateProject(editProject.id, {
          name: name.trim(),
          description: description.trim() || undefined,
          color: color || undefined,
        })
      } else {
        await createProject(name.trim(), description.trim() || undefined, color || undefined)
      }

      // Close dialog and reset form
      onOpenChange(false)
      setName('')
      setDescription('')
      setColor('#3B82F6')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save project')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCancel = () => {
    onOpenChange(false)
    setName(editProject?.name || '')
    setDescription(editProject?.description || '')
    setColor(editProject?.color || '#3B82F6')
    setError(null)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{editProject ? 'Edit Project' : 'Create New Project'}</DialogTitle>
            <DialogDescription>
              {editProject
                ? 'Update your project details'
                : 'Organize your conversations into projects'}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            {/* Project Name */}
            <div className="grid gap-2">
              <Label htmlFor="name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                placeholder="e.g., Research, Analysis"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={100}
                disabled={isSubmitting}
                autoFocus
              />
              <p className="text-xs text-muted-foreground">{name.length}/100 characters</p>
            </div>

            {/* Description */}
            <div className="grid gap-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Textarea
                id="description"
                placeholder="Brief description of this project"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={500}
                disabled={isSubmitting}
                rows={3}
              />
              <p className="text-xs text-muted-foreground">{description.length}/500 characters</p>
            </div>

            {/* Color Picker */}
            <div className="grid gap-2">
              <Label>Color</Label>
              <ProjectColorPicker value={color} onChange={setColor} disabled={isSubmitting} />
            </div>

            {/* Error Message */}
            {error && (
              <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">{error}</div>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={handleCancel} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : editProject ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
