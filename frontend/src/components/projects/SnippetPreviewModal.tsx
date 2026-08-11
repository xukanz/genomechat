/**
 * SnippetPreviewModal - Modal to preview snippet details with syntax highlighting
 */

import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Edit2, Trash2, Copy, Check } from 'lucide-react'
import { useState, useEffect } from 'react'
import type { Snippet } from '../../types/project'
import { Button } from '../ui/button'
import { cn } from '../../lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
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

interface SnippetPreviewModalProps {
  snippet: Snippet | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onEdit: (snippet?: Snippet) => void
  onDelete: (snippetId: string) => void
  onToggle: (snippetId: string) => void
  isLoading?: boolean
}

const categoryLabels: Record<string, string> = {
  visualization: 'Visualization',
  data_processing: 'Data Processing',
  statistics: 'Statistics',
  file_operations: 'File Operations',
  domain_specific: 'Domain Specific',
  custom: 'Custom',
}

const categoryColors: Record<string, string> = {
  visualization: 'bg-purple-100 text-purple-800',
  data_processing: 'bg-blue-100 text-blue-800',
  statistics: 'bg-green-100 text-green-800',
  file_operations: 'bg-yellow-100 text-yellow-800',
  domain_specific: 'bg-pink-100 text-pink-800',
  custom: 'bg-gray-100 text-gray-800',
}

export function SnippetPreviewModal({
  snippet,
  open,
  onOpenChange,
  onEdit,
  onDelete,
  onToggle,
  isLoading = false,
}: SnippetPreviewModalProps) {
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [copied, setCopied] = useState(false)
  const [localEnabled, setLocalEnabled] = useState(snippet?.enabled ?? true)
  const [isToggling, setIsToggling] = useState(false)

  // Sync local state with snippet prop
  useEffect(() => {
    if (snippet) {
      setLocalEnabled(snippet.enabled)
    }
  }, [snippet?.enabled, snippet])

  if (!snippet) return null

  const handleEdit = () => {
    onEdit(snippet)
    onOpenChange(false)
  }

  const handleDelete = () => {
    onDelete(snippet.id)
    setShowDeleteDialog(false)
    onOpenChange(false)
  }

  const handleToggle = async () => {
    // Optimistic update with animation
    setIsToggling(true)
    setLocalEnabled(!localEnabled)

    // Call the actual toggle
    onToggle(snippet.id)

    // Brief delay for animation feel
    setTimeout(() => setIsToggling(false), 300)
  }

  const handleCopy = async () => {
    await navigator.clipboard.writeText(snippet.code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[700px] max-h-[85vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <DialogTitle className="text-lg font-semibold truncate">
                  {snippet.name}
                </DialogTitle>
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
                      categoryColors[snippet.category] || categoryColors.custom
                    }`}
                  >
                    {categoryLabels[snippet.category] || snippet.category}
                  </span>
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium transition-all duration-300",
                      localEnabled
                        ? 'bg-green-100 text-green-800'
                        : 'bg-gray-100 text-gray-600'
                    )}
                  >
                    {localEnabled ? 'Active' : 'Disabled'}
                  </span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {/* Custom Toggle Switch with Animation */}
                <button
                  type="button"
                  role="switch"
                  aria-checked={localEnabled}
                  onClick={handleToggle}
                  disabled={isLoading || isToggling}
                  title={localEnabled ? 'Disable snippet' : 'Enable snippet'}
                  className={cn(
                    "relative inline-flex h-8 w-14 shrink-0 cursor-pointer items-center rounded-full transition-all duration-300 ease-in-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
                    localEnabled
                      ? "bg-green-500 shadow-[inset_0_2px_4px_rgba(0,0,0,0.1)]"
                      : "bg-gray-300 shadow-[inset_0_2px_4px_rgba(0,0,0,0.1)]",
                    isToggling && "scale-95"
                  )}
                >
                  <span
                    className={cn(
                      "pointer-events-none block h-6 w-6 rounded-full bg-white shadow-md ring-0 transition-all duration-300 ease-in-out",
                      localEnabled
                        ? "translate-x-7"
                        : "translate-x-1",
                      isToggling && "scale-90"
                    )}
                  />
                </button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={handleEdit}
                  disabled={isLoading}
                  title="Edit snippet"
                >
                  <Edit2 className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-destructive hover:text-destructive"
                  onClick={() => setShowDeleteDialog(true)}
                  disabled={isLoading}
                  title="Delete snippet"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </DialogHeader>

          {/* Description */}
          {snippet.description && (
            <p className="text-sm text-muted-foreground mt-2">
              {snippet.description}
            </p>
          )}

          {/* Code Block with Syntax Highlighting */}
          <div className="flex-1 overflow-hidden mt-4 rounded-lg border border-slate-200">
            <div className="flex items-center justify-between bg-slate-800 px-4 py-2 border-b border-slate-700">
              <span className="text-xs font-medium text-slate-400">Python</span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-slate-400 hover:text-white hover:bg-slate-700"
                onClick={handleCopy}
              >
                {copied ? (
                  <>
                    <Check className="h-3.5 w-3.5 mr-1" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5 mr-1" />
                    Copy
                  </>
                )}
              </Button>
            </div>
            <div className="overflow-auto max-h-[400px]">
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
                  minWidth: '3em',
                  paddingRight: '1em',
                  color: '#6B7280',
                  userSelect: 'none',
                }}
              >
                {snippet.code}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Footer Info */}
          <div className="flex items-center justify-between text-xs text-muted-foreground mt-4 pt-4 border-t">
            <span>
              Created: {new Date(snippet.created_at).toLocaleDateString()}
            </span>
            <span>
              Updated: {new Date(snippet.updated_at).toLocaleDateString()}
            </span>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Snippet?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete <strong>{snippet.name}</strong>? This action cannot
              be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
