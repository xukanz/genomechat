/**
 * Dialog shown when user tries to switch conversations while a long-running
 * or deep research stream is active.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Button } from '../ui/button'
import { useConversationStore } from '../../store/conversationStore'
import { AlertTriangle, FlaskConical } from 'lucide-react'

export function SwitchConversationDialog() {
  const {
    showSwitchConfirmation,
    isDeepResearch,
    confirmSwitch,
    cancelSwitch,
  } = useConversationStore()

  return (
    <Dialog open={showSwitchConfirmation} onOpenChange={(open) => !open && cancelSwitch()}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <div className="flex items-center gap-3">
            {isDeepResearch ? (
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100">
                <FlaskConical className="h-5 w-5 text-indigo-600" />
              </div>
            ) : (
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-100">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
              </div>
            )}
            <DialogTitle>
              {isDeepResearch ? 'Deep Research in Progress' : 'Response in Progress'}
            </DialogTitle>
          </div>
          <DialogDescription className="pt-2">
            {isDeepResearch ? (
              <>
                A deep research task is currently running. Switching conversations will{' '}
                <strong>cancel this research</strong> and all progress will be lost.
              </>
            ) : (
              <>
                A response is being generated. Switching conversations will{' '}
                <strong>stop the current response</strong>. This cannot be undone.
              </>
            )}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={cancelSwitch}>
            {isDeepResearch ? 'Keep Researching' : 'Continue Response'}
          </Button>
          <Button
            variant="destructive"
            onClick={confirmSwitch}
            className="bg-red-600 hover:bg-red-700"
          >
            {isDeepResearch ? 'Cancel Research' : 'Stop & Switch'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
