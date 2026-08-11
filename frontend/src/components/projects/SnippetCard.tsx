/**
 * SnippetCard - Display a single code snippet with actions
 */

import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Edit2, Trash2, ChevronDown, ChevronUp } from 'lucide-react'
import type { Snippet } from '../../types/project'
import { Button } from '../ui/button'
import { cn } from '../../lib/utils'
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

interface SnippetCardProps {
  snippet: Snippet
  onEdit: (snippet: Snippet) => void
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
  visualization: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  data_processing: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  statistics: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  file_operations: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  domain_specific: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-300',
  custom: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
}

export function SnippetCard({
  snippet,
  onEdit,
  onDelete,
  onToggle,
  isLoading = false,
}: SnippetCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)

  const handleDelete = () => {
    onDelete(snippet.id)
    setShowDeleteDialog(false)
  }

  return (
    <>
      <div
        className={`border rounded-lg p-4 ${
          snippet.enabled
            ? 'bg-card'
            : 'bg-muted/50 opacity-75'
        }`}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-medium truncate">{snippet.name}</h3>
              <span
                className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                  categoryColors[snippet.category] || categoryColors.custom
                }`}
              >
                {categoryLabels[snippet.category] || snippet.category}
              </span>
              {!snippet.enabled && (
                <span className="inline-flex items-center rounded-full border px-2 py-1 text-xs font-medium text-muted-foreground">
                  Disabled
                </span>
              )}
            </div>
            {snippet.description && (
              <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                {snippet.description}
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            {/* Custom Toggle Switch */}
            <button
              type="button"
              role="switch"
              aria-checked={snippet.enabled}
              onClick={() => onToggle(snippet.id)}
              disabled={isLoading}
              title={snippet.enabled ? 'Disable snippet' : 'Enable snippet'}
              className={cn(
                "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
                snippet.enabled
                  ? "bg-green-500 shadow-inner"
                  : "bg-gray-300 shadow-inner"
              )}
            >
              <span
                className={cn(
                  "pointer-events-none block h-4 w-4 rounded-full bg-white shadow-lg ring-0 transition-all duration-200",
                  snippet.enabled
                    ? "translate-x-6"
                    : "translate-x-1"
                )}
              />
            </button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onEdit(snippet)}
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

        {/* Code Preview Toggle */}
        <Button
          variant="ghost"
          size="sm"
          className="mt-2 w-full justify-start text-muted-foreground hover:text-foreground"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? (
            <>
              <ChevronUp className="h-4 w-4 mr-1" />
              Hide code
            </>
          ) : (
            <>
              <ChevronDown className="h-4 w-4 mr-1" />
              Show code
            </>
          )}
        </Button>

        {/* Code Block with Syntax Highlighting */}
        {isExpanded && (
          <div className="mt-2 rounded-md overflow-hidden border border-slate-200">
            <SyntaxHighlighter
              language="python"
              style={vscDarkPlus}
              customStyle={{
                margin: 0,
                borderRadius: '0.375rem',
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
              {snippet.code}
            </SyntaxHighlighter>
          </div>
        )}
      </div>

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
