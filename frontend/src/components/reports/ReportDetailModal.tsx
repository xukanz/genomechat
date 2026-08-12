/**
 * Report Detail Modal
 * Shows full report content with navigation to source conversation
 */

import { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { ExternalLink, Calendar, Copy, Check } from "lucide-react"
import { Button } from "../ui/button"
import { markdownUrlTransform } from "../../lib/markdownUrl"
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "../ui/dialog"
import type { Report } from "../../types/report"

interface ReportDetailModalProps {
    report: Report | null
    open: boolean
    onClose: () => void
    onGoToConversation: (conversationId: string) => void
}

export function ReportDetailModal({
    report,
    open,
    onClose,
    onGoToConversation,
}: ReportDetailModalProps) {
    const [copiedSuccess, setCopiedSuccess] = useState(false)

    if (!report) return null

    const formattedDate = new Date(report.created_at).toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    })

    const handleGoToConversation = () => {
        onGoToConversation(report.conversation_id)
        onClose()
    }

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(report.content)
            setCopiedSuccess(true)
            setTimeout(() => setCopiedSuccess(false), 2000)
        } catch (error) {
            console.error("Failed to copy:", error)
        }
    }

    return (
        <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
            <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
                <DialogHeader className="flex-shrink-0 pb-4 border-b">
                    <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                            <DialogTitle className="text-xl font-semibold text-foreground mb-2 pr-8">
                                {report.title}
                            </DialogTitle>
                            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                                <span className="flex items-center gap-1.5">
                                    <Calendar className="h-3.5 w-3.5" />
                                    {formattedDate}
                                </span>
                                <span className="text-indigo-600">
                                    From: {report.conversation_title}
                                </span>
                            </div>
                        </div>
                    </div>
                </DialogHeader>

                <div className="flex-1 overflow-y-auto py-4">
                    <div className="prose prose-slate max-w-none dark:prose-invert prose-p:leading-relaxed prose-pre:p-0">
                        <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            urlTransform={markdownUrlTransform}
                        >
                            {report.content}
                        </ReactMarkdown>
                    </div>
                </div>

                <div className="flex-shrink-0 flex items-center justify-between pt-4 border-t">
                    <Button
                        variant="outline"
                        onClick={onClose}
                    >
                        Close
                    </Button>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            onClick={handleCopy}
                            className="gap-2"
                        >
                            {copiedSuccess ? (
                                <>
                                    <Check className="h-4 w-4 text-green-500" />
                                    Copied!
                                </>
                            ) : (
                                <>
                                    <Copy className="h-4 w-4" />
                                    Copy
                                </>
                            )}
                        </Button>
                        <Button
                            onClick={handleGoToConversation}
                            className="gap-2"
                        >
                            <ExternalLink className="h-4 w-4" />
                            Go to Conversation
                        </Button>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
