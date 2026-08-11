import { useState, useEffect, useMemo } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Bot, Copy, ThumbsUp, ThumbsDown, ChevronDown, FileText, Download, X, ChevronLeft, ChevronRight, Bookmark, BookmarkCheck, Check } from "lucide-react"
import { Button } from "../ui/button"
import { Input } from "../ui/input"
import { ThinkingProcess } from "./ThinkingProcess"
import { AgentActivityPanel } from "./AgentActivityPanel"
import { useConversationStore } from "../../store/conversationStore"
import { useReportStore } from "../../store/reportStore"
import { useFeedbackStore } from "../../store/feedbackStore"
import type { Message } from "../../hooks/useChat"
import type { FeedbackType } from "../../types/feedback"

const markdownComponents = {
    code: ({ inline, children, ...props }: any) => {
        if (inline) {
            return (
                <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-primary" {...props}>
                    {children}
                </code>
            )
        }

        return (
            <div className="relative rounded-lg overflow-hidden my-4 border bg-[#1E1E1E]">
                <div className="flex items-center justify-between px-4 py-2 bg-[#2D2D2D] border-b border-[#404040]">
                    <span className="text-xs text-gray-400">Code</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6 text-gray-400 hover:text-white">
                        <Copy className="h-3 w-3" />
                    </Button>
                </div>
                <div className="p-4 overflow-x-auto">
                    <code className="text-sm font-mono text-gray-300 block" {...props}>
                        {children}
                    </code>
                </div>
            </div>
        )
    }
}

function MarkdownContent({ content }: { content?: string }) {
    if (!content?.trim()) {
        return null
    }

    return (
        <div className="prose prose-slate max-w-none dark:prose-invert prose-p:leading-relaxed prose-pre:p-0">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents as any}>
                {content}
            </ReactMarkdown>
        </div>
    )
}

interface MessageBubbleProps {
    message: Message
    messageIndex?: number
}

export function MessageBubble({ message, messageIndex = 0 }: MessageBubbleProps) {
    const isUser = message.role === "user"
    const isSystem = message.role === "system"
    const [openResponses, setOpenResponses] = useState<Record<string, boolean>>({})
    const [lightboxOpen, setLightboxOpen] = useState(false)
    const [lightboxIndex, setLightboxIndex] = useState(0)

    // Bookmark state
    const [showBookmarkInput, setShowBookmarkInput] = useState(false)
    const [bookmarkTitle, setBookmarkTitle] = useState("")
    const [isSaving, setIsSaving] = useState(false)
    const [savedSuccess, setSavedSuccess] = useState(false)
    const [showRemoveConfirm, setShowRemoveConfirm] = useState(false)
    const [isRemoving, setIsRemoving] = useState(false)

    // Feedback state
    const [showFeedbackNote, setShowFeedbackNote] = useState(false)
    const [feedbackNote, setFeedbackNote] = useState("")
    const [pendingFeedbackType, setPendingFeedbackType] = useState<FeedbackType | null>(null)
    const [isSavingFeedback, setIsSavingFeedback] = useState(false)
    const [copiedSuccess, setCopiedSuccess] = useState(false)

    // Stores
    const { currentConversationId } = useConversationStore()
    const { createReport, deleteReport, loadBookmarksForConversation, bookmarkedMessages } = useReportStore()
    const { submitFeedback, removeFeedback, loadFeedbackForConversation, feedbackMap } = useFeedbackStore()

    // Check if this message is already bookmarked (subscribe to bookmarkedMessages for reactivity)
    const existingReportId = useMemo(() => {
        if (!currentConversationId) return null
        const key = `${currentConversationId}:${messageIndex}`
        return bookmarkedMessages[key] || null
    }, [currentConversationId, messageIndex, bookmarkedMessages])

    const isBookmarked = !!existingReportId

    // Get current feedback for this message (subscribe to feedbackMap for reactivity)
    const currentFeedback = useMemo(() => {
        if (!currentConversationId) return null
        const key = `${currentConversationId}:${messageIndex}`
        return feedbackMap[key]?.feedbackType || null
    }, [currentConversationId, messageIndex, feedbackMap])

    // Load bookmarks and feedback when conversation changes
    useEffect(() => {
        if (currentConversationId && messageIndex === 0) {
            // Only load once per conversation (when first message mounts)
            loadBookmarksForConversation(currentConversationId)
            loadFeedbackForConversation(currentConversationId)
        }
    }, [currentConversationId, messageIndex, loadBookmarksForConversation, loadFeedbackForConversation])

    // Get only image files for lightbox
    const imageFiles = message.files?.filter(f => f.isImage) || []

    // Handle escape key to close lightbox
    useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && lightboxOpen) {
                setLightboxOpen(false)
            }
        }
        window.addEventListener('keydown', handleEscape)
        return () => window.removeEventListener('keydown', handleEscape)
    }, [lightboxOpen])

    // Navigate between images in lightbox
    const goToPrevious = () => {
        setLightboxIndex((prev) => (prev === 0 ? imageFiles.length - 1 : prev - 1))
    }

    const goToNext = () => {
        setLightboxIndex((prev) => (prev === imageFiles.length - 1 ? 0 : prev + 1))
    }

    // Handle bookmark save
    const handleBookmarkSave = async () => {
        if (!currentConversationId || !bookmarkTitle.trim() || !message.content) {
            return
        }

        setIsSaving(true)
        try {
            await createReport({
                conversation_id: currentConversationId,
                title: bookmarkTitle.trim(),
                content: message.content,
                message_index: messageIndex,
            })
            setSavedSuccess(true)
            setShowBookmarkInput(false)
            setBookmarkTitle("")
            // Reset success indicator after 2 seconds
            setTimeout(() => setSavedSuccess(false), 2000)
        } catch (error) {
            console.error("Failed to save report:", error)
        } finally {
            setIsSaving(false)
        }
    }

    // Handle bookmark cancel
    const handleBookmarkCancel = () => {
        setShowBookmarkInput(false)
        setBookmarkTitle("")
    }

    // Handle bookmark remove
    const handleBookmarkRemove = async () => {
        if (!existingReportId) return

        setIsRemoving(true)
        try {
            await deleteReport(existingReportId)
            setShowRemoveConfirm(false)
        } catch (error) {
            console.error("Failed to remove report:", error)
        } finally {
            setIsRemoving(false)
        }
    }

    // Handle bookmark button click
    const handleBookmarkClick = () => {
        if (isBookmarked) {
            // Show remove confirmation
            setShowRemoveConfirm(true)
        } else {
            // Show save input
            setShowBookmarkInput(!showBookmarkInput)
        }
    }

    // Handle copy to clipboard
    const handleCopy = async () => {
        if (message.content) {
            try {
                await navigator.clipboard.writeText(message.content)
                setCopiedSuccess(true)
                setTimeout(() => setCopiedSuccess(false), 2000)
            } catch (error) {
                console.error("Failed to copy:", error)
            }
        }
    }

    // Handle thumbs click
    const handleThumbClick = (type: FeedbackType) => {
        if (currentFeedback === type) {
            // Toggle off - remove feedback
            handleRemoveFeedback()
        } else {
            // Show note input for new feedback
            setPendingFeedbackType(type)
            setShowFeedbackNote(true)
        }
    }

    // Submit feedback
    const handleFeedbackSubmit = async () => {
        if (!currentConversationId || !pendingFeedbackType) return

        setIsSavingFeedback(true)
        try {
            await submitFeedback({
                conversation_id: currentConversationId,
                message_index: messageIndex,
                feedback_type: pendingFeedbackType,
                note: feedbackNote.trim() || undefined,
            })
            setShowFeedbackNote(false)
            setFeedbackNote("")
            setPendingFeedbackType(null)
        } catch (error) {
            console.error("Failed to submit feedback:", error)
        } finally {
            setIsSavingFeedback(false)
        }
    }

    // Remove feedback
    const handleRemoveFeedback = async () => {
        if (!currentConversationId) return

        try {
            await removeFeedback(currentConversationId, messageIndex)
        } catch (error) {
            console.error("Failed to remove feedback:", error)
        }
    }

    // Cancel feedback input
    const handleFeedbackCancel = () => {
        setShowFeedbackNote(false)
        setFeedbackNote("")
        setPendingFeedbackType(null)
    }

    if (isSystem) {
        return null
    }

    if (isUser) {
        return (
            <div className="w-full py-2 flex justify-end">
                <div className="max-w-[66%] rounded-2xl bg-slate-200 text-slate-900 px-5 py-3 text-sm shadow-sm border border-slate-300">
                    <MarkdownContent content={message.content} />
                </div>
            </div>
        )
    }

    return (
        <div className="w-full py-4">
            <div className="space-y-3 rounded-3xl border border-slate-200 bg-white px-6 py-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Research Assistant</div>

                {message.agentActivities && message.agentActivities.length > 0 && (
                    <AgentActivityPanel activities={message.agentActivities} />
                )}

                {message.thinking && (
                    <ThinkingProcess content={message.thinking} isStreaming={message.isStreaming} />
                )}

                {message.agentResponses && message.agentResponses.length > 0 && (
                    <div className="space-y-3">
                        {message.agentResponses.map((response) => {
                            const isOpen = openResponses[response.id] ?? false

                            const toggleResponse = () =>
                                setOpenResponses((prev) => ({
                                    ...prev,
                                    [response.id]: !isOpen,
                                }))

                            return (
                                <div key={response.id} className="rounded-xl border bg-muted/20">
                                    <button
                                        type="button"
                                        onClick={toggleResponse}
                                        className="flex w-full items-center justify-between px-4 py-2 text-xs uppercase tracking-wide text-muted-foreground border-b border-border/60"
                                    >
                                        <div className="flex items-center gap-2 text-[11px] font-semibold normal-case text-foreground">
                                            <Bot className="h-4 w-4" />
                                            <span>{response.agent}</span>
                                        </div>
                                        <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                                            <span>{isOpen ? "Hide" : "Show"}</span>
                                            <ChevronDown className={`h-3 w-3 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                                        </div>
                                    </button>
                                    {isOpen && (
                                        <div className="p-4">
                                            <MarkdownContent content={response.content} />
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                    </div>
                )}

                {message.files && message.files.length > 0 && (
                    <div className="space-y-2">
                        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Generated Files
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                            {message.files.map((file) => (
                                <div key={file.id}>
                                    {file.isImage ? (
                                        <div 
                                            className="rounded-lg border bg-muted/20 overflow-hidden cursor-pointer hover:border-primary/50 transition-colors group"
                                            onClick={() => {
                                                const imageIndex = imageFiles.findIndex(f => f.id === file.id)
                                                setLightboxIndex(imageIndex)
                                                setLightboxOpen(true)
                                            }}
                                        >
                                            <div className="relative h-48 overflow-hidden bg-slate-100 dark:bg-slate-800">
                                                <img 
                                                    src={file.url} 
                                                    alt={file.filename}
                                                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                                                    loading="lazy"
                                                />
                                                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors flex items-center justify-center">
                                                    <span className="text-white text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity bg-black/70 px-3 py-1 rounded-full">
                                                        Click to enlarge
                                                    </span>
                                                </div>
                                            </div>
                                            <div className="px-3 py-2 bg-background/50 text-xs text-muted-foreground">
                                                <div className="truncate">{file.filename}</div>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="rounded-lg border bg-muted/20 overflow-hidden">
                                            <div className="px-3 py-2 flex items-center justify-between">
                                                <div className="flex items-center gap-2 min-w-0">
                                                    <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                                                    <span className="text-sm truncate">{file.filename}</span>
                                                </div>
                                                <a 
                                                    href={file.url} 
                                                    download={file.filename}
                                                    className="text-primary hover:underline text-sm flex items-center gap-1 flex-shrink-0 ml-2"
                                                >
                                                    <Download className="h-3 w-3" />
                                                    Download
                                                </a>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Image Lightbox Modal */}
                {lightboxOpen && imageFiles.length > 0 && (
                    <div 
                        className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center"
                        onClick={() => setLightboxOpen(false)}
                    >
                        {/* Close button */}
                        <button
                            className="absolute top-4 right-4 text-white hover:text-gray-300 transition-colors"
                            onClick={() => setLightboxOpen(false)}
                        >
                            <X className="h-8 w-8" />
                        </button>

                        {/* Previous button */}
                        {imageFiles.length > 1 && (
                            <button
                                className="absolute left-4 text-white hover:text-gray-300 transition-colors"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    goToPrevious()
                                }}
                            >
                                <ChevronLeft className="h-12 w-12" />
                            </button>
                        )}

                        {/* Image container */}
                        <div 
                            className="max-w-7xl max-h-[90vh] flex flex-col items-center gap-4 px-16"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <img 
                                src={imageFiles[lightboxIndex].url}
                                alt={imageFiles[lightboxIndex].filename}
                                className="max-w-full max-h-[80vh] object-contain rounded-lg"
                            />
                            <div className="text-white text-sm bg-black/50 px-4 py-2 rounded-full">
                                {imageFiles[lightboxIndex].filename}
                                {imageFiles.length > 1 && (
                                    <span className="ml-2 text-gray-400">
                                        ({lightboxIndex + 1} / {imageFiles.length})
                                    </span>
                                )}
                            </div>
                        </div>

                        {/* Next button */}
                        {imageFiles.length > 1 && (
                            <button
                                className="absolute right-4 text-white hover:text-gray-300 transition-colors"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    goToNext()
                                }}
                            >
                                <ChevronRight className="h-12 w-12" />
                            </button>
                        )}
                    </div>
                )}

                <MarkdownContent content={message.content} />

                {/* Bookmark input popover */}
                {showBookmarkInput && (
                    <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50 border">
                        <Bookmark className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                        <Input
                            type="text"
                            placeholder="Enter report title..."
                            value={bookmarkTitle}
                            onChange={(e) => setBookmarkTitle(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter") handleBookmarkSave()
                                if (e.key === "Escape") handleBookmarkCancel()
                            }}
                            className="h-8 text-sm"
                            autoFocus
                            disabled={isSaving}
                        />
                        <Button
                            size="sm"
                            onClick={handleBookmarkSave}
                            disabled={!bookmarkTitle.trim() || isSaving}
                            className="h-8"
                        >
                            {isSaving ? "Saving..." : "Save"}
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={handleBookmarkCancel}
                            disabled={isSaving}
                            className="h-8"
                        >
                            Cancel
                        </Button>
                    </div>
                )}

                {/* Remove bookmark confirmation */}
                {showRemoveConfirm && (
                    <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 border border-red-200">
                        <BookmarkCheck className="h-4 w-4 text-red-500 flex-shrink-0" />
                        <span className="text-sm text-red-700">Remove this bookmark?</span>
                        <div className="flex-1" />
                        <Button
                            size="sm"
                            variant="destructive"
                            onClick={handleBookmarkRemove}
                            disabled={isRemoving}
                            className="h-8"
                        >
                            {isRemoving ? "Removing..." : "Remove"}
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setShowRemoveConfirm(false)}
                            disabled={isRemoving}
                            className="h-8"
                        >
                            Cancel
                        </Button>
                    </div>
                )}

                {/* Feedback note input */}
                {showFeedbackNote && (
                    <div className="flex items-center gap-2 p-3 rounded-lg bg-muted/50 border">
                        {pendingFeedbackType === "positive" ? (
                            <ThumbsUp className="h-4 w-4 text-green-500 flex-shrink-0" />
                        ) : (
                            <ThumbsDown className="h-4 w-4 text-red-500 flex-shrink-0" />
                        )}
                        <Input
                            type="text"
                            placeholder="Add a note (optional)..."
                            value={feedbackNote}
                            onChange={(e) => setFeedbackNote(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter") handleFeedbackSubmit()
                                if (e.key === "Escape") handleFeedbackCancel()
                            }}
                            className="h-8 text-sm"
                            autoFocus
                            disabled={isSavingFeedback}
                        />
                        <Button
                            size="sm"
                            onClick={handleFeedbackSubmit}
                            disabled={isSavingFeedback}
                            className="h-8"
                        >
                            {isSavingFeedback ? "Saving..." : "Submit"}
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={handleFeedbackCancel}
                            disabled={isSavingFeedback}
                            className="h-8"
                        >
                            Cancel
                        </Button>
                    </div>
                )}

                <div className="flex items-center gap-2 pt-2">
                    {/* Copy button */}
                    <Button
                        variant="ghost"
                        size="icon"
                        className={`h-8 w-8 ${copiedSuccess ? 'text-green-500' : 'text-muted-foreground hover:text-primary'}`}
                        onClick={handleCopy}
                        title={copiedSuccess ? "Copied!" : "Copy to clipboard"}
                    >
                        {copiedSuccess ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    </Button>
                    {/* Bookmark button */}
                    <Button
                        variant="ghost"
                        size="icon"
                        className={`h-8 w-8 ${
                            savedSuccess
                                ? 'text-green-500'
                                : isBookmarked
                                ? 'text-amber-500 hover:text-amber-600'
                                : 'text-muted-foreground hover:text-primary'
                        }`}
                        onClick={handleBookmarkClick}
                        disabled={!currentConversationId || savedSuccess}
                        title={
                            savedSuccess
                                ? "Saved to reports"
                                : isBookmarked
                                ? "Remove bookmark"
                                : "Save to reports"
                        }
                    >
                        {savedSuccess ? (
                            <Check className="h-4 w-4" />
                        ) : isBookmarked ? (
                            <BookmarkCheck className="h-4 w-4" />
                        ) : (
                            <Bookmark className="h-4 w-4" />
                        )}
                    </Button>
                    <div className="flex-1" />
                    {/* Thumbs up button */}
                    <Button
                        variant="ghost"
                        size="icon"
                        className={`h-8 w-8 ${
                            currentFeedback === 'positive'
                                ? 'text-green-500 hover:text-green-600'
                                : 'text-muted-foreground hover:text-primary'
                        }`}
                        onClick={() => handleThumbClick('positive')}
                        disabled={!currentConversationId}
                        title={currentFeedback === 'positive' ? "Remove feedback" : "Good response"}
                    >
                        <ThumbsUp className={`h-4 w-4 ${currentFeedback === 'positive' ? 'fill-current' : ''}`} />
                    </Button>
                    {/* Thumbs down button */}
                    <Button
                        variant="ghost"
                        size="icon"
                        className={`h-8 w-8 ${
                            currentFeedback === 'negative'
                                ? 'text-red-500 hover:text-red-600'
                                : 'text-muted-foreground hover:text-primary'
                        }`}
                        onClick={() => handleThumbClick('negative')}
                        disabled={!currentConversationId}
                        title={currentFeedback === 'negative' ? "Remove feedback" : "Poor response"}
                    >
                        <ThumbsDown className={`h-4 w-4 ${currentFeedback === 'negative' ? 'fill-current' : ''}`} />
                    </Button>
                </div>
            </div>
        </div>
    )
}

