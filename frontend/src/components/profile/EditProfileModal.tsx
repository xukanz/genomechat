/**
 * EditProfileModal - Modal for editing user profile (name)
 */

import { useState, useEffect } from 'react'
import { useAuthStore } from '../../store/authStore'
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
import { User, Loader2 } from 'lucide-react'

interface EditProfileModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EditProfileModal({ open, onOpenChange }: EditProfileModalProps) {
  const { user, updateProfile, isLoading, error, clearError } = useAuthStore()

  const [name, setName] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  // Initialize name when modal opens
  useEffect(() => {
    if (open && user) {
      setName(user.name)
      setLocalError(null)
      clearError()
    }
  }, [open, user, clearError])

  const handleSave = async () => {
    if (!name.trim()) {
      setLocalError('Name cannot be empty')
      return
    }

    if (name.trim() === user?.name) {
      onOpenChange(false)
      return
    }

    try {
      await updateProfile(name.trim())
      onOpenChange(false)
    } catch {
      // Error is handled by the store
    }
  }

  const handleCancel = () => {
    onOpenChange(false)
    setLocalError(null)
    clearError()
  }

  const displayError = localError || error

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Edit Profile
          </DialogTitle>
          <DialogDescription>
            Update your profile information.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              placeholder="Enter your name"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                setLocalError(null)
              }}
              disabled={isLoading}
              autoFocus
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="email" className="text-muted-foreground">
              Email
            </Label>
            <Input
              id="email"
              value={user?.email || ''}
              disabled
              className="bg-muted"
            />
            <p className="text-xs text-muted-foreground">
              Email cannot be changed.
            </p>
          </div>

          {displayError && (
            <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">
              {displayError}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={handleCancel} disabled={isLoading}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={isLoading}>
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              'Save'
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
