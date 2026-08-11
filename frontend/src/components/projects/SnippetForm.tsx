/**
 * SnippetForm - Form for creating/editing code snippets
 */

import { useState, useEffect } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { Snippet, SnippetCategory, SnippetCreate, SnippetUpdate } from '../../types/project'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Textarea } from '../ui/textarea'
import { Label } from '../ui/label'
import { Switch } from '../ui/switch'
import { Loader2, Eye, EyeOff } from 'lucide-react'

interface SnippetFormProps {
  snippet?: Snippet | null
  onSubmit: (data: SnippetCreate | SnippetUpdate) => Promise<void>
  onCancel: () => void
  isSubmitting?: boolean
}

const categoryOptions: { value: SnippetCategory; label: string }[] = [
  { value: 'visualization', label: 'Visualization' },
  { value: 'data_processing', label: 'Data Processing' },
  { value: 'statistics', label: 'Statistics' },
  { value: 'file_operations', label: 'File Operations' },
  { value: 'domain_specific', label: 'Domain Specific' },
  { value: 'custom', label: 'Custom' },
]

export function SnippetForm({
  snippet,
  onSubmit,
  onCancel,
  isSubmitting = false,
}: SnippetFormProps) {
  const [name, setName] = useState('')
  const [category, setCategory] = useState<SnippetCategory>('custom')
  const [description, setDescription] = useState('')
  const [code, setCode] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [showPreview, setShowPreview] = useState(false)

  const isEditing = !!snippet

  // Populate form when editing
  useEffect(() => {
    if (snippet) {
      setName(snippet.name)
      setCategory(snippet.category)
      setDescription(snippet.description || '')
      setCode(snippet.code)
      setEnabled(snippet.enabled)
    } else {
      // Reset form when creating new
      setName('')
      setCategory('custom')
      setDescription('')
      setCode('')
      setEnabled(true)
    }
    setErrors({})
  }, [snippet])

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {}

    if (!name.trim()) {
      newErrors.name = 'Name is required'
    } else if (name.length > 100) {
      newErrors.name = 'Name must be 100 characters or less'
    }

    if (!code.trim()) {
      newErrors.code = 'Code is required'
    } else if (code.length > 10000) {
      newErrors.code = 'Code must be 10,000 characters or less'
    }

    if (!description.trim()) {
      newErrors.description = 'Description is required'
    } else if (description.length > 500) {
      newErrors.description = 'Description must be 500 characters or less'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!validate()) {
      return
    }

    if (isEditing) {
      // For updates, only send changed fields
      const updates: SnippetUpdate = {}
      if (name !== snippet!.name) updates.name = name
      if (category !== snippet!.category) updates.category = category
      if (description !== (snippet!.description || '')) updates.description = description || null
      if (code !== snippet!.code) updates.code = code
      if (enabled !== snippet!.enabled) updates.enabled = enabled

      await onSubmit(updates)
    } else {
      // For create, send all fields
      const data: SnippetCreate = {
        name: name.trim(),
        category,
        description: description.trim(),
        code: code.trim(),
        enabled,
      }
      await onSubmit(data)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Name */}
      <div className="space-y-2">
        <Label htmlFor="name">Name *</Label>
        <Input
          id="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g., TCR Diversity Analysis"
          disabled={isSubmitting}
          className={errors.name ? 'border-destructive' : ''}
        />
        {errors.name && (
          <p className="text-sm text-destructive">{errors.name}</p>
        )}
      </div>

      {/* Category */}
      <div className="space-y-2">
        <Label htmlFor="category">Category</Label>
        <select
          id="category"
          value={category}
          onChange={(e) => setCategory(e.target.value as SnippetCategory)}
          disabled={isSubmitting}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {categoryOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {/* Description */}
      <div className="space-y-2">
        <Label htmlFor="description">Description *</Label>
        <Textarea
          id="description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Brief description of what this snippet does..."
          rows={2}
          disabled={isSubmitting}
          className={errors.description ? 'border-destructive' : ''}
        />
        {errors.description && (
          <p className="text-sm text-destructive">{errors.description}</p>
        )}
        <p className="text-xs text-muted-foreground">
          {description.length}/500 characters
        </p>
      </div>

      {/* Code */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="code">Code *</Label>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-muted-foreground hover:text-foreground"
            onClick={() => setShowPreview(!showPreview)}
            disabled={!code.trim()}
          >
            {showPreview ? (
              <>
                <EyeOff className="h-3.5 w-3.5 mr-1" />
                Hide Preview
              </>
            ) : (
              <>
                <Eye className="h-3.5 w-3.5 mr-1" />
                Show Preview
              </>
            )}
          </Button>
        </div>

        {showPreview && code.trim() ? (
          <div className="rounded-md overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between bg-slate-800 px-3 py-1.5 border-b border-slate-700">
              <span className="text-xs font-medium text-slate-400">Python Preview</span>
            </div>
            <div className="max-h-[300px] overflow-auto">
              <SyntaxHighlighter
                language="python"
                style={vscDarkPlus}
                customStyle={{
                  margin: 0,
                  borderRadius: 0,
                  fontSize: '13px',
                  lineHeight: '1.5',
                }}
                showLineNumbers
                lineNumberStyle={{
                  minWidth: '2.5em',
                  paddingRight: '1em',
                  color: '#6B7280',
                  userSelect: 'none',
                }}
              >
                {code}
              </SyntaxHighlighter>
            </div>
          </div>
        ) : (
          <Textarea
            id="code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="# Your Python code here..."
            rows={10}
            className={`font-mono text-sm ${errors.code ? 'border-destructive' : ''}`}
            disabled={isSubmitting}
          />
        )}
        {errors.code && (
          <p className="text-sm text-destructive">{errors.code}</p>
        )}
        <p className="text-xs text-muted-foreground">
          {code.length}/10,000 characters
        </p>
      </div>

      {/* Enabled Toggle */}
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label htmlFor="enabled">Enabled</Label>
          <p className="text-sm text-muted-foreground">
            Enabled snippets are injected into the Coder Agent prompt
          </p>
        </div>
        <Switch
          id="enabled"
          checked={enabled}
          onCheckedChange={setEnabled}
          disabled={isSubmitting}
        />
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-2 pt-4">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {isEditing ? 'Save Changes' : 'Create Snippet'}
        </Button>
      </div>
    </form>
  )
}
