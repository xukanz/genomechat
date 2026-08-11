/**
 * DatabaseDetailModal - Modal for viewing database details and connecting
 */

import { useState, useEffect } from 'react'
import { useDatabaseStore } from '../../store/databaseStore'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog'
import { Button } from '../ui/button'
import { Database, Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
import type { DatabaseInfo } from '../../types/database'

interface DatabaseDetailModalProps {
  database: DatabaseInfo | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function DatabaseDetailModal({ database, open, onOpenChange }: DatabaseDetailModalProps) {
  const { connectToDatabase, isConnecting, connectionError, clearConnectionError } = useDatabaseStore()
  const [connectionSuccess, setConnectionSuccess] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)

  // Reset state when modal opens/closes
  useEffect(() => {
    if (open) {
      setConnectionSuccess(false)
      setValidationError(null)
      clearConnectionError()
    }
  }, [open, clearConnectionError])

  // Auto-close modal on successful connection after brief delay
  useEffect(() => {
    if (connectionSuccess) {
      const timer = setTimeout(() => {
        onOpenChange(false)
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [connectionSuccess, onOpenChange])

  const handleConnect = async () => {
    if (!database) return
    setValidationError(null)

    const success = await connectToDatabase(database.id)
    if (success) {
      setConnectionSuccess(true)
    }
  }

  if (!database) return null

  const isAlreadyConnected = database.is_active
  const connectDisabled = isConnecting || isAlreadyConnected || connectionSuccess

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Database className="h-5 w-5 text-primary" />
            {database.display_name}
          </DialogTitle>
          <DialogDescription>
            {database.domain
              ? database.domain.replace(/\b\w/g, (c) => c.toUpperCase())
              : 'Research Database'}
            {' \u2022 '}
            {database.database_type.toUpperCase()}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-4">
          {/* Full Description */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-foreground">Description</h4>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {database.description}
            </p>
          </div>

          {/* Technical Details */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-foreground">Technical Details</h4>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="text-muted-foreground">Database Type:</div>
              <div className="font-medium">{database.database_type}</div>
              <div className="text-muted-foreground">SQL Dialect:</div>
              <div className="font-medium">{database.sql_dialect}</div>
              <div className="text-muted-foreground">Status:</div>
              <div className="font-medium">
                {database.is_active ? (
                  <span className="text-green-600">Connected</span>
                ) : (
                  <span className="text-slate-600">Available</span>
                )}
              </div>
            </div>
          </div>

          {/* Validation Error */}
          {validationError && !connectionSuccess && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700">
              <AlertCircle className="h-5 w-5 mt-0.5 flex-shrink-0" />
              <div className="text-sm">{validationError}</div>
            </div>
          )}

          {/* Connection Error Message */}
          {connectionError && !connectionSuccess && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700">
              <AlertCircle className="h-5 w-5 mt-0.5 flex-shrink-0" />
              <div className="text-sm">
                <p className="font-medium">Connection failed</p>
                <p className="text-red-600">{connectionError}</p>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isConnecting}
          >
            Cancel
          </Button>
          <Button
            onClick={handleConnect}
            disabled={connectDisabled}
          >
            {isConnecting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Connecting...
              </>
            ) : isAlreadyConnected ? (
              <>
                <CheckCircle2 className="mr-2 h-4 w-4" />
                Connected
              </>
            ) : connectionSuccess ? (
              <>
                <CheckCircle2 className="mr-2 h-4 w-4" />
                Connected!
              </>
            ) : (
              'Connect'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
