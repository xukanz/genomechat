/**
 * ShareProjectModal - Modal for sharing a project with other users
 */

import { useState, useEffect, useCallback } from 'react'
import { useProjectStore } from '../../store/projectStore'
import { searchUsers } from '../../services/api'
import type { Project, ProjectShare, UserSummary } from '../../types/project'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Users, X, Search, UserPlus, Loader2 } from 'lucide-react'

interface ShareProjectModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  project: Project
}

export function ShareProjectModal({ open, onOpenChange, project }: ShareProjectModalProps) {
  const { shareProject, removeShare } = useProjectStore()

  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<UserSummary[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [isSharing, setIsSharing] = useState(false)
  const [isRemoving, setIsRemoving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Debounced search
  useEffect(() => {
    if (searchQuery.length < 2) {
      setSearchResults([])
      return
    }

    const timer = setTimeout(async () => {
      setIsSearching(true)
      try {
        const result = await searchUsers(searchQuery, 10)
        // Filter out users already shared with
        const existingUserIds = project.shares.map((s) => s.user_id)
        const filteredResults = result.users.filter(
          (u) => !existingUserIds.includes(u.id)
        )
        setSearchResults(filteredResults)
      } catch (err) {
        console.error('Search failed:', err)
        setSearchResults([])
      } finally {
        setIsSearching(false)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [searchQuery, project.shares])

  const handleShare = useCallback(
    async (user: UserSummary) => {
      setError(null)
      setIsSharing(true)

      try {
        await shareProject(project.id, user.id)
        setSearchQuery('')
        setSearchResults([])
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to share project')
      } finally {
        setIsSharing(false)
      }
    },
    [project.id, shareProject]
  )

  const handleRemoveShare = useCallback(
    async (userId: string) => {
      setError(null)
      setIsRemoving(userId)

      try {
        await removeShare(project.id, userId)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to remove share')
      } finally {
        setIsRemoving(null)
      }
    },
    [project.id, removeShare]
  )

  const handleClose = () => {
    onOpenChange(false)
    setSearchQuery('')
    setSearchResults([])
    setError(null)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            Share Project
          </DialogTitle>
          <DialogDescription>
            Share "{project.name}" with other users. They will have read-only access.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Search Input */}
          <div className="grid gap-2">
            <Label htmlFor="search">Add people</Label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="search"
                placeholder="Search by email or name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
                disabled={isSharing}
              />
              {isSearching && (
                <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
              )}
            </div>

            {/* Search Results Dropdown */}
            {searchResults.length > 0 && (
              <div className="border rounded-md bg-popover shadow-md max-h-48 overflow-y-auto">
                {searchResults.map((user) => (
                  <button
                    key={user.id}
                    type="button"
                    className="w-full px-3 py-2 text-left hover:bg-accent flex items-center justify-between gap-2"
                    onClick={() => handleShare(user)}
                    disabled={isSharing}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{user.name}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {user.email}
                      </p>
                    </div>
                    <UserPlus className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  </button>
                ))}
              </div>
            )}

            {searchQuery.length >= 2 && !isSearching && searchResults.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-2">
                No users found
              </p>
            )}
          </div>

          {/* Current Shares */}
          <div className="grid gap-2">
            <Label>Shared with ({project.shares.length})</Label>
            {project.shares.length === 0 ? (
              <p className="text-sm text-muted-foreground py-2">
                This project is not shared with anyone yet.
              </p>
            ) : (
              <div className="border rounded-md divide-y max-h-48 overflow-y-auto">
                {project.shares.map((share: ProjectShare) => (
                  <div
                    key={share.user_id}
                    className="px-3 py-2 flex items-center justify-between gap-2"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {share.user_name || 'Unknown'}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">
                        {share.user_email}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      onClick={() => handleRemoveShare(share.user_id)}
                      disabled={isRemoving === share.user_id}
                    >
                      {isRemoving === share.user_id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <X className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Error Message */}
          {error && (
            <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">
              {error}
            </div>
          )}
        </div>

        <div className="flex justify-end">
          <Button variant="outline" onClick={handleClose}>
            Done
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
