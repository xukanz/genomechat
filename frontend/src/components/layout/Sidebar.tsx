import * as React from "react"
import { motion } from "framer-motion"
import { useState, useEffect, useMemo } from "react"
import { createPortal } from "react-dom"
import {
  Box,
  Code,
  Database,
  FileText,
  MessageCircle,
  PanelLeftClose,
  Plus,
  Trash2,
  Loader2,
  MoreVertical,
  Pencil,
  Check,
  X,
  Download,
  FolderInput,
  ChevronRight,
  Package,
  LogOut,
  User
} from "lucide-react"
import { Button } from "../ui/button"
import { useUIStore } from "../../store/uiStore"
import { useConversationStore } from "../../store/conversationStore"
import { useArtifactStore } from "../../store/artifactStore"
import { useReportStore } from "../../store/reportStore"
import { useAuthStore } from "../../store/authStore"
import { useProjectStore } from "../../store/projectStore"
import { useDatabaseStore } from "../../store/databaseStore"
import { useSnippetStore } from "../../store/snippetStore"
import { cn } from "../../lib/utils"
import logoMark from "../../assets/logo.svg"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "../ui/dropdown-menu"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog"
import { useNavigate } from "react-router-dom"
import { ProjectSection, SnippetManagerModal, SnippetPreviewModal } from "../projects"
import type { Snippet } from "../../types/project"
import { ReportDetailModal } from "../reports"
import { EditProfileModal } from "../profile/EditProfileModal"
import { SwitchConversationDialog } from "../chat/SwitchConversationDialog"
import { DatabaseDetailModal } from "../databases"
import type { Report } from "../../types/report"
import type { DatabaseInfo } from "../../types/database"
import { BRANDING } from "../../config/branding"

const railTabs = [
  { id: "messages", label: "Chats", icon: MessageCircle },
  { id: "artifacts", label: "Artifacts", icon: Box },
  { id: "reports", label: "Reports", icon: FileText },
  { id: "snippets", label: "Snippets", icon: Code },
  { id: "databases", label: "Databases", icon: Database }
]

// Database type labels for display.
// The backend already sends a human-readable domain per profile ("clinical
// genetics", "statistical genetics", "genome annotation"), so use it rather
// than mapping storage engines to hardcoded names — a duckdb profile is not
// inherently any one kind of data.
const getDatabaseTypeLabel = (domain: string): string => {
  if (!domain) return "Research Database"
  return domain.replace(/\b\w/g, (char) => char.toUpperCase())
}

// Mock savedReports removed - now using reportStore

const getProfileInitials = (name?: string, email?: string) => {
  if (name && name.trim().length > 0) {
    const initials = name
      .trim()
      .split(/[\s_-]+/)
      .filter(Boolean)
      .map((part) => part[0]?.toUpperCase())
      .join("")

    if (initials) {
      return initials.slice(0, 2)
    }
  }

  if (email && email.length > 0) {
    const localPart = email.split("@")[0]
    if (localPart) {
      return localPart.slice(0, 2).toUpperCase()
    }
  }

  return "IC"
}
// Move to Project submenu component
function MoveToProjectMenu({ conversationId, currentProjectId }: { conversationId: string; currentProjectId?: string | null }) {
  const { projects, moveConversation } = useProjectStore()
  const { loadConversations } = useConversationStore()
  const [isMoving, setIsMoving] = React.useState(false)

  const handleMoveToProject = async (projectId: string) => {
    if (projectId === currentProjectId) return // Already in this project
    
    setIsMoving(true)
    try {
      await moveConversation(conversationId, projectId)
      // Reload conversations to reflect the change
      await loadConversations(currentProjectId || undefined)
    } catch (error) {
      console.error('Failed to move conversation:', error)
    } finally {
      setIsMoving(false)
    }
  }

  return (
    <>
      {projects.map((project) => (
        <DropdownMenuItem
          key={project.id}
          onClick={() => handleMoveToProject(project.id)}
          disabled={isMoving || project.id === currentProjectId}
          className={cn(
            project.id === currentProjectId && 'opacity-50 cursor-not-allowed'
          )}
        >
          <div
            className="w-2 h-2 rounded-full mr-2 flex-shrink-0"
            style={{ backgroundColor: project.color || '#6B7280' }}
          />
          <span className="truncate">{project.name}</span>
          {project.id === currentProjectId && (
            <Check className="ml-auto h-4 w-4" />
          )}
        </DropdownMenuItem>
      ))}
    </>
  )
}

export function Sidebar() {
  const { isSidebarOpen, toggleSidebar, setSidebarOpen } = useUIStore()
  const {
    conversations,
    currentConversationId,
    isLoading,
    error,
    loadConversations,
    requestConversationSwitch,
    deleteConversation,
    updateConversationTitle,
    clearError
  } = useConversationStore()
  const {
    projects,
    selectedProjectId,
    setSelectedProject
  } = useProjectStore()
  const {
    artifacts,
    artifactUrls,
    isLoading: artifactsLoading,
    error: artifactsError,
    hasMore,
    loadArtifacts,
    loadMoreArtifacts,
    downloadArtifact
  } = useArtifactStore()
  const {
    reports,
    isLoading: reportsLoading,
    error: reportsError,
    loadReports,
    deleteReport
  } = useReportStore()
  const {
    databases,
    isLoading: databasesLoading,
    error: databasesError,
    loadDatabases
  } = useDatabaseStore()
  const {
    snippets,
    isLoading: snippetsLoading,
    error: snippetsError,
    loadSnippets,
    toggleSnippet,
    deleteSnippet
  } = useSnippetStore()
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const collapsed = !isSidebarOpen
  const [activeTab, setActiveTab] = useState<typeof railTabs[number]["id"]>("messages")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState<string>("")
  const [deleteDialogOpen, setDeleteDialogOpen] = useState<boolean>(false)
  const [conversationToDelete, setConversationToDelete] = useState<{ id: string; title: string } | null>(null)
  const [downloadingFileId, setDownloadingFileId] = useState<string | null>(null)
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const [lightboxImageUrl, setLightboxImageUrl] = useState<string | null>(null)
  const [lightboxFilename, setLightboxFilename] = useState<string>('')
  const [reportToDelete, setReportToDelete] = useState<{ id: string; title: string } | null>(null)
  const [deleteReportDialogOpen, setDeleteReportDialogOpen] = useState(false)
  const [selectedReport, setSelectedReport] = useState<Report | null>(null)
  const [reportModalOpen, setReportModalOpen] = useState(false)
  const [editProfileModalOpen, setEditProfileModalOpen] = useState(false)
  const [selectedDatabase, setSelectedDatabase] = useState<DatabaseInfo | null>(null)
  const [databaseModalOpen, setDatabaseModalOpen] = useState(false)
  const [snippetProjectId, setSnippetProjectId] = useState<string | null>(null)
  const [snippetModalOpen, setSnippetModalOpen] = useState(false)
  const [selectedSnippet, setSelectedSnippet] = useState<Snippet | null>(null)
  const [snippetPreviewOpen, setSnippetPreviewOpen] = useState(false)
  const profileDisplayName = useMemo(() => {
    if (user?.name?.trim()) {
      return user.name.trim()
    }
    if (user?.email) {
      return user.email.split("@")[0]
    }
    return `${BRANDING.name} User`
  }, [user?.name, user?.email])

  const profileSubtext = useMemo(() => {
    if (user?.email) {
      return user.email
    }
    return "Manage account"
  }, [user?.email])

  const profileInitials = useMemo(() => getProfileInitials(user?.name, user?.email), [user?.name, user?.email])

  // Load conversations on mount
  useEffect(() => {
    if (activeTab === "messages") {
      loadConversations()
    }
  }, [activeTab, loadConversations])

  // Load artifacts when artifacts tab is active
  useEffect(() => {
    if (activeTab === "artifacts") {
      loadArtifacts(undefined, selectedProjectId || undefined)
    }
  }, [activeTab, selectedProjectId, loadArtifacts])

  // Load reports when reports tab is active
  useEffect(() => {
    if (activeTab === "reports") {
      loadReports(selectedProjectId)
    }
  }, [activeTab, selectedProjectId, loadReports])

  // Load databases when databases tab is active
  useEffect(() => {
    if (activeTab === "databases") {
      loadDatabases()
    }
  }, [activeTab, loadDatabases])

  // Load snippets when snippets tab is active and project is selected
  useEffect(() => {
    if (activeTab === "snippets" && snippetProjectId) {
      loadSnippets(snippetProjectId)
    }
  }, [activeTab, snippetProjectId, loadSnippets])

  // Set default snippet project when switching to snippets tab
  useEffect(() => {
    if (activeTab === "snippets" && !snippetProjectId && projects.length > 0) {
      const defaultProject = projects.find(p => p.is_default) || projects[0]
      setSnippetProjectId(defaultProject.id)
    }
  }, [activeTab, snippetProjectId, projects])

  // Handle escape key to close lightbox
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && lightboxOpen) {
        setLightboxOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [lightboxOpen])

  // Handle artifact download
  const handleDownload = async (fileId: string) => {
    setDownloadingFileId(fileId)
    try {
      await downloadArtifact(fileId)
    } catch (err) {
      console.error('Download failed:', err)
    } finally {
      setDownloadingFileId(null)
    }
  }

  // Handle load more button click
  const handleLoadMore = () => {
    loadMoreArtifacts(undefined)
  }

  const ensureExpanded = () => setSidebarOpen(true)

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const handleNewChat = () => {
    // Use requestConversationSwitch to show confirmation if streaming
    requestConversationSwitch(null)
    clearError()
  }

  const handleSelectConversation = (conversationId: string) => {
    // Use requestConversationSwitch to show confirmation if streaming
    requestConversationSwitch(conversationId)
  }

  const handleOpenDeleteDialog = (conversationId: string, title: string) => {
    setConversationToDelete({ id: conversationId, title })
    setDeleteDialogOpen(true)
  }

  const handleConfirmDelete = async () => {
    if (conversationToDelete) {
      await deleteConversation(conversationToDelete.id)
      setDeleteDialogOpen(false)
      setConversationToDelete(null)
    }
  }

  const handleCancelDelete = () => {
    setDeleteDialogOpen(false)
    setConversationToDelete(null)
  }

  // Report delete handlers
  const handleOpenDeleteReportDialog = (reportId: string, title: string) => {
    setReportToDelete({ id: reportId, title })
    setDeleteReportDialogOpen(true)
  }

  const handleConfirmDeleteReport = async () => {
    if (reportToDelete) {
      await deleteReport(reportToDelete.id)
      setDeleteReportDialogOpen(false)
      setReportToDelete(null)
    }
  }

  const handleCancelDeleteReport = () => {
    setDeleteReportDialogOpen(false)
    setReportToDelete(null)
  }

  // Report modal handlers
  const handleOpenReportModal = (report: Report) => {
    setSelectedReport(report)
    setReportModalOpen(true)
  }

  const handleCloseReportModal = () => {
    setReportModalOpen(false)
    setSelectedReport(null)
  }

  const handleGoToConversation = (conversationId: string) => {
    // Use requestConversationSwitch to show confirmation if streaming
    requestConversationSwitch(conversationId)
    setActiveTab("messages")
    handleCloseReportModal()
  }

  const handleStartRename = (conversationId: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(conversationId)
    setEditingTitle(currentTitle)
  }

  const handleSaveRename = async (conversationId: string) => {
    if (editingTitle.trim() && editingTitle !== conversations.find(c => c.id === conversationId)?.title) {
      await updateConversationTitle(conversationId, editingTitle.trim())
    }
    setEditingId(null)
    setEditingTitle("")
  }

  const handleCancelRename = () => {
    setEditingId(null)
    setEditingTitle("")
  }

  const handleRenameKeyDown = (e: React.KeyboardEvent, conversationId: string) => {
    if (e.key === 'Enter') {
      handleSaveRename(conversationId)
    } else if (e.key === 'Escape') {
      handleCancelRename()
    }
  }

  // Group conversations by date
  const groupConversationsByDate = () => {
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)
    
    // Sort conversations by updated_at descending (most recent first)
    const sortedConversations = [...conversations].sort((a, b) => {
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    })

    // Group by actual dates
    const dateGroups = new Map<string, typeof conversations>()
    
    sortedConversations.forEach(conv => {
      const convDate = new Date(conv.updated_at)
      const convDay = new Date(convDate.getFullYear(), convDate.getMonth(), convDate.getDate())
      
      let groupTitle: string
      if (convDay.getTime() === today.getTime()) {
        groupTitle = "Today"
      } else if (convDay.getTime() === yesterday.getTime()) {
        groupTitle = "Yesterday"
      } else {
        // Format as "Jan 9, 2026"
        groupTitle = convDate.toLocaleDateString('en-US', { 
          month: 'short', 
          day: 'numeric',
          year: 'numeric'
        })
      }
      
      if (!dateGroups.has(groupTitle)) {
        dateGroups.set(groupTitle, [])
      }
      dateGroups.get(groupTitle)!.push(conv)
    })

    // Convert to array format
    return Array.from(dateGroups.entries()).map(([title, items]) => ({ title, items }))
  }

  return (
    <div className="relative z-10 flex h-full flex-shrink-0 border-r bg-slate-50/80 backdrop-blur-xl">
      <div className="flex w-[76px] flex-col items-center justify-between border-r border-white/60 bg-white/80 px-3 py-5">
        <div className="flex flex-col items-center gap-3">
          <button
            type="button"
            onClick={() => navigate("/")}
            className="flex h-12 w-12 items-center justify-center rounded-full bg-white shadow-lg shadow-[0_12px_28px_rgba(0,102,204,0.25)] overflow-hidden focus:outline-none focus:ring-2 focus:ring-[#0066CC] focus:ring-offset-2 focus:ring-offset-white cursor-pointer hover:scale-105 transition-transform"
            aria-label="Go to home"
          >
            <img
              src={logoMark}
              alt={`${BRANDING.name} logo`}
              className="h-16 w-16 rounded-full object-cover"
            />
          </button>
        </div>

        <div className="flex flex-1 w-full flex-col items-center gap-2 py-6">
          {railTabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => {
                setActiveTab(id)
                ensureExpanded()
              }}
              aria-label={label}
              className={cn(
                "group relative flex h-12 w-12 items-center justify-center rounded-2xl border border-transparent text-brand-darkBlue transition",
                activeTab === id
                  ? "border-[#66B5FF] bg-white text-brand-blue shadow-[0_8px_20px_rgba(0,102,204,0.15)]"
                  : "opacity-70 hover:bg-brand-lightGrey hover:opacity-100"
              )}
            >
              <Icon className="h-5 w-5" />
              {collapsed && (
                <span className="pointer-events-none absolute left-full ml-3 hidden rounded-xl bg-slate-900 px-3 py-1 text-xs font-medium text-white shadow-lg z-50 group-hover:block">
                  {label}
                </span>
              )}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={ensureExpanded}
          className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-darkBlue text-white shadow-inner shadow-[0_6px_16px_rgba(0,64,128,0.45)] focus:outline-none focus:ring-2 focus:ring-[#0066CC]"
          aria-label="Profile"
        >
          {profileInitials}
        </button>
      </div>

      <motion.aside
        initial={false}
        animate={{ width: collapsed ? 0 : 240 }}
        transition={{ duration: 0.28, ease: "easeInOut" }}
        className="relative flex h-full overflow-hidden bg-slate-50/95"
      >
        <div className="pointer-events-auto absolute inset-0 flex h-full w-[240px] flex-col">
          <div className="flex items-center justify-between gap-3 px-4 h-14 border-b border-slate-200">
            <div className="flex flex-col text-foreground">
              <span className="text-sm font-semibold">
                {activeTab === "messages"
                  ? "Chat History"
                  : activeTab === "artifacts"
                  ? "Artifacts"
                  : activeTab === "reports"
                  ? "Reports"
                  : activeTab === "snippets"
                  ? "Code Snippets"
                  : "Databases"}
              </span>
              <span className="text-xs text-muted-foreground">
                {activeTab === "messages"
                  ? "Recent conversations"
                  : activeTab === "artifacts"
                  ? "Generated outputs"
                  : activeTab === "reports"
                  ? "Saved research findings"
                  : activeTab === "snippets"
                  ? "Project code patterns"
                  : "Available connections"}
              </span>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleSidebar}
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
            >
              <PanelLeftClose className="h-4 w-4" />
            </Button>
          </div>

          {activeTab === "messages" && (
            <div className="px-4 py-3">
              <Button
                onClick={handleNewChat}
                className="w-full justify-center gap-2 h-9 rounded-full bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800"
                aria-label="Start new research"
              >
                <Plus className="h-4 w-4" />
                <span>New Research</span>
              </Button>
            </div>
          )}

          {activeTab === "messages" && (
            <>
              {/* Projects Section */}
              <ProjectSection />

              {/* Conversations List */}
              <div className="flex-1 overflow-y-auto px-2 py-2 space-y-4 scrollbar-hide">
              {isLoading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              )}

              {error && (
                <div className="px-4 py-3 mx-2 rounded-lg bg-red-50 border border-red-200">
                  <p className="text-sm text-red-600">{error}</p>
                  <button 
                    onClick={clearError}
                    className="text-xs text-red-500 hover:text-red-700 mt-1"
                  >
                    Dismiss
                  </button>
                </div>
              )}

              {!isLoading && !error && conversations.length === 0 && (
                <div className="px-4 py-8 text-center">
                  <p className="text-sm text-muted-foreground">No conversations yet</p>
                  <p className="text-xs text-muted-foreground mt-1">Start a new chat to begin</p>
                </div>
              )}

              {!isLoading && !error && groupConversationsByDate().map((section) => (
                <div key={section.title}>
                  <div className="px-2 text-[11px] font-semibold text-muted-foreground/60 mb-1.5">
                    {section.title}
                  </div>
                  <div className="space-y-0.5">
                    {section.items.map((conversation) => {
                      const isEditing = editingId === conversation.id
                      
                      return (
                        <div
                          key={conversation.id}
                          className={cn(
                            "group relative w-full rounded-lg px-2 py-2 text-left transition flex items-center",
                            currentConversationId === conversation.id
                              ? "bg-slate-200"
                              : "hover:bg-slate-100"
                          )}
                        >
                          {isEditing ? (
                            <div className="flex items-center gap-1 flex-1">
                              <input
                                type="text"
                                value={editingTitle}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEditingTitle(e.target.value)}
                                onKeyDown={(e) => handleRenameKeyDown(e, conversation.id)}
                                className="flex-1 px-2 py-1 text-sm border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-slate-400"
                                autoFocus
                              />
                              <button
                                onClick={() => handleSaveRename(conversation.id)}
                                className="p-1 hover:bg-slate-200 rounded"
                                aria-label="Save"
                              >
                                <Check className="h-3.5 w-3.5 text-green-600" />
                              </button>
                              <button
                                onClick={handleCancelRename}
                                className="p-1 hover:bg-slate-200 rounded"
                                aria-label="Cancel"
                              >
                                <X className="h-3.5 w-3.5 text-slate-500" />
                              </button>
                            </div>
                          ) : (
                            <>
                              <button
                                onClick={() => handleSelectConversation(conversation.id)}
                                className="w-full text-left pr-8 flex items-center"
                                title={conversation.title}
                              >
                                <span className={cn(
                                  "block truncate text-sm",
                                  currentConversationId === conversation.id
                                    ? "font-medium text-slate-900"
                                    : "font-normal text-foreground"
                                )}>
                                  {conversation.title}
                                </span>
                              </button>
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <button
                                    className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-slate-200 rounded"
                                    aria-label="More options"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <MoreVertical className="h-4 w-4 text-slate-600" />
                                  </button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-48">
                                  <DropdownMenuItem
                                    onClick={(e) => handleStartRename(conversation.id, conversation.title, e)}
                                  >
                                    <Pencil className="mr-2 h-4 w-4" />
                                    <span>Rename</span>
                                  </DropdownMenuItem>
                                  
                                  <DropdownMenuSub>
                                    <DropdownMenuSubTrigger>
                                      <FolderInput className="mr-2 h-4 w-4" />
                                      <span>Move to Project</span>
                                      <ChevronRight className="ml-auto h-4 w-4" />
                                    </DropdownMenuSubTrigger>
                                    <DropdownMenuSubContent className="w-48">
                                      <MoveToProjectMenu conversationId={conversation.id} currentProjectId={conversation.project_id} />
                                    </DropdownMenuSubContent>
                                  </DropdownMenuSub>

                                  <DropdownMenuItem
                                    onClick={() => handleOpenDeleteDialog(conversation.id, conversation.title)}
                                    className="text-red-600 focus:text-red-600"
                                  >
                                    <Trash2 className="mr-2 h-4 w-4" />
                                    <span>Delete</span>
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
              </div>
            </>
          )}

          {activeTab === "artifacts" && (
            <>
              {/* Projects List for Artifacts */}
              <div className="border-b border-border">
                <div className="flex items-center justify-between px-3 py-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <span>Projects</span>
                    {projects.length > 0 && (
                      <span className="text-xs text-muted-foreground">({projects.length})</span>
                    )}
                  </div>
                </div>

                <div className="space-y-0.5 pb-2">
                  {/* Default project first */}
                  {projects
                    .filter((p) => p.is_default)
                    .map((project) => (
                      <div
                        key={project.id}
                        className={cn(
                          'group relative flex items-start gap-2 px-3 py-2 cursor-pointer transition-colors',
                          'hover:bg-accent/50',
                          selectedProjectId === project.id && 'bg-accent'
                        )}
                        onClick={() => setSelectedProject(project.id)}
                      >
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0 mt-1"
                          style={{ backgroundColor: project.color || '#6B7280' }}
                        />
                        <div className="flex-1 min-w-0 pr-16">
                          <div className="text-sm font-medium text-foreground truncate">{project.name}</div>
                          {project.description && (
                            <div className="text-xs text-muted-foreground truncate">{project.description}</div>
                          )}
                        </div>
                        <div
                          className={cn(
                            'absolute right-3 top-2 flex items-center justify-center min-w-[44px] h-6 px-2.5 rounded-full text-xs font-medium',
                            'bg-slate-200 text-slate-700'
                          )}
                        >
                          <Package className="h-3 w-3 mr-1" />
                          <span>{project.artifact_count || 0}</span>
                        </div>
                      </div>
                    ))}

                  {/* Other projects */}
                  {projects
                    .filter((p) => !p.is_default)
                    .map((project) => (
                      <div
                        key={project.id}
                        className={cn(
                          'group relative flex items-start gap-2 px-3 py-2 cursor-pointer transition-colors',
                          'hover:bg-accent/50',
                          selectedProjectId === project.id && 'bg-accent'
                        )}
                        onClick={() => setSelectedProject(project.id)}
                      >
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0 mt-1"
                          style={{ backgroundColor: project.color || '#6B7280' }}
                        />
                        <div className="flex-1 min-w-0 pr-16">
                          <div className="text-sm font-medium text-foreground truncate">{project.name}</div>
                          {project.description && (
                            <div className="text-xs text-muted-foreground truncate">{project.description}</div>
                          )}
                        </div>
                        <div
                          className={cn(
                            'absolute right-3 top-2 flex items-center justify-center min-w-[44px] h-6 px-2.5 rounded-full text-xs font-medium',
                            'bg-slate-200 text-slate-700'
                          )}
                        >
                          <Package className="h-3 w-3 mr-1" />
                          <span>{project.artifact_count || 0}</span>
                        </div>
                      </div>
                    ))}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto px-4 py-2 space-y-4 scrollbar-hide">
                {artifactsLoading && artifacts.length === 0 && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
                  </div>
                )}
                {artifactsError && (
                  <div className="rounded-xl bg-red-50 border border-red-200 p-4 text-sm text-red-700">
                    {artifactsError}
                  </div>
                )}
                {!artifactsLoading && !artifactsError && artifacts.length === 0 && (
                  <div className="text-center py-8 text-sm text-muted-foreground">
                    No images found
                  </div>
                )}
                {!artifactsLoading && artifacts.map((artifact) => {
                  const sizeKB = (artifact.size_bytes / 1024).toFixed(1)
                  const sizeMB = (artifact.size_bytes / 1048576).toFixed(1)
                  const displaySize = artifact.size_bytes > 1048576 ? `${sizeMB} MB` : `${sizeKB} KB`
                  const filename = artifact.s3_key.split('/').pop() || 'file'
                  const isDownloading = downloadingFileId === artifact.file_id
                  const isImage = artifact.content_type.match(/^(png|jpg|jpeg|gif|svg|webp)$/i)
                  const imageUrl = artifactUrls[artifact.file_id]
                  
                  return (
                    <div
                      key={artifact.file_id}
                      className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-[0_5px_25px_rgba(15,23,42,0.04)]"
                    >
                      <div className="mb-3">
                        <p className="text-sm font-semibold text-foreground mb-1 break-words">{filename}</p>
                        <div className="flex items-center gap-2 text-xs flex-wrap">
                          <span className="text-muted-foreground capitalize">{artifact.file_type.replace('_', ' ')}</span>
                          <span className="text-muted-foreground">•</span>
                          <span className="text-muted-foreground uppercase">{artifact.content_type}</span>
                          <span className="text-muted-foreground">•</span>
                          <span className="text-muted-foreground">{displaySize}</span>
                        </div>
                      </div>
                      
                      {/* Display image preview with click-to-open lightbox */}
                      {isImage && imageUrl && (
                        <div 
                          className="mb-3 rounded-lg overflow-hidden bg-slate-50 cursor-pointer transition-all hover:opacity-90 max-h-48"
                          onClick={() => {
                            setLightboxImageUrl(imageUrl)
                            setLightboxFilename(filename)
                            setLightboxOpen(true)
                          }}
                          title="Click to view full size"
                        >
                          <img 
                            src={imageUrl} 
                            alt={filename}
                            className="w-full h-auto object-cover max-h-48"
                            loading="lazy"
                          />
                        </div>
                      )}
                      {isImage && !imageUrl && (
                        <div className="mb-3 rounded-lg bg-slate-50 h-32 flex items-center justify-center">
                          <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
                        </div>
                      )}

                      {artifact.conversation_title && (
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-xs text-indigo-600 truncate">From: {artifact.conversation_title}</span>
                        </div>
                      )}
                      <Button
                        onClick={() => handleDownload(artifact.file_id)}
                        disabled={isDownloading}
                        size="sm"
                        variant="outline"
                        className="w-full"
                      >
                        {isDownloading ? (
                          <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Downloading...
                          </>
                        ) : (
                          <>
                            <Download className="mr-2 h-4 w-4" />
                            Download
                          </>
                        )}
                      </Button>
                    </div>
                  )
                })}
                
                {/* Load More button */}
                {hasMore && !artifactsLoading && artifacts.length > 0 && (
                  <div className="flex justify-center py-4">
                    <Button
                      onClick={handleLoadMore}
                      size="sm"
                      variant="outline"
                      className="w-full max-w-xs"
                    >
                      Load More
                    </Button>
                  </div>
                )}
                
                {/* Loading more indicator */}
                {artifactsLoading && artifacts.length > 0 && (
                  <div className="flex items-center justify-center py-4">
                    <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                  </div>
                )}
                
                {/* End of list indicator */}
                {!hasMore && artifacts.length > 0 && (
                  <div className="text-center py-4 text-xs text-muted-foreground">
                    No more artifacts
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === "reports" && (
            <>
              {/* Projects List for Reports */}
              <div className="border-b border-border">
                <div className="flex items-center justify-between px-3 py-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <span>Projects</span>
                    {projects.length > 0 && (
                      <span className="text-xs text-muted-foreground">({projects.length})</span>
                    )}
                  </div>
                </div>

                <div className="space-y-0.5 pb-2">
                  {/* Default project first */}
                  {projects
                    .filter((p) => p.is_default)
                    .map((project) => (
                      <div
                        key={project.id}
                        className={cn(
                          'group relative flex items-start gap-2 px-3 py-2 cursor-pointer transition-colors',
                          'hover:bg-accent/50',
                          selectedProjectId === project.id && 'bg-accent'
                        )}
                        onClick={() => setSelectedProject(project.id)}
                      >
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0 mt-1"
                          style={{ backgroundColor: project.color || '#6B7280' }}
                        />
                        <div className="flex-1 min-w-0 pr-16">
                          <div className="text-sm font-medium text-foreground truncate">{project.name}</div>
                          {project.description && (
                            <div className="text-xs text-muted-foreground truncate">{project.description}</div>
                          )}
                        </div>
                        <div
                          className={cn(
                            'absolute right-3 top-2 flex items-center justify-center min-w-[44px] h-6 px-2.5 rounded-full text-xs font-medium',
                            'bg-slate-200 text-slate-700'
                          )}
                        >
                          <FileText className="h-3 w-3 mr-1" />
                          <span>{project.report_count || 0}</span>
                        </div>
                      </div>
                    ))}

                  {/* Other projects */}
                  {projects
                    .filter((p) => !p.is_default)
                    .map((project) => (
                      <div
                        key={project.id}
                        className={cn(
                          'group relative flex items-start gap-2 px-3 py-2 cursor-pointer transition-colors',
                          'hover:bg-accent/50',
                          selectedProjectId === project.id && 'bg-accent'
                        )}
                        onClick={() => setSelectedProject(project.id)}
                      >
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0 mt-1"
                          style={{ backgroundColor: project.color || '#6B7280' }}
                        />
                        <div className="flex-1 min-w-0 pr-16">
                          <div className="text-sm font-medium text-foreground truncate">{project.name}</div>
                          {project.description && (
                            <div className="text-xs text-muted-foreground truncate">{project.description}</div>
                          )}
                        </div>
                        <div
                          className={cn(
                            'absolute right-3 top-2 flex items-center justify-center min-w-[44px] h-6 px-2.5 rounded-full text-xs font-medium',
                            'bg-slate-200 text-slate-700'
                          )}
                        >
                          <FileText className="h-3 w-3 mr-1" />
                          <span>{project.report_count || 0}</span>
                        </div>
                      </div>
                    ))}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scrollbar-hide">
                {reportsLoading && reports.length === 0 && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                )}

                {reportsError && (
                  <div className="rounded-xl bg-red-50 border border-red-200 p-4 text-sm text-red-700">
                    {reportsError}
                  </div>
                )}

                {!reportsLoading && !reportsError && reports.length === 0 && (
                  <div className="text-center py-8">
                    <FileText className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
                    <p className="text-sm text-muted-foreground">No saved reports yet</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Bookmark AI responses to save them here
                    </p>
                  </div>
                )}

                {!reportsLoading && reports.map((report) => {
                  const formattedDate = new Date(report.created_at).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                  })

                  return (
                    <div
                      key={report.id}
                      className="group relative rounded-2xl border border-slate-200/80 bg-white/80 p-4 transition hover:border-indigo-200 hover:shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <button
                          type="button"
                          className="flex-1 text-left"
                          onClick={() => handleOpenReportModal(report)}
                        >
                          <h3 className="text-sm font-semibold text-foreground leading-snug mb-2">
                            {report.title}
                          </h3>
                          <p className="text-xs text-muted-foreground mb-1">{formattedDate}</p>
                          <p className="text-xs text-indigo-600 mb-3">From: {report.conversation_title}</p>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleOpenDeleteReportDialog(report.id, report.title)
                          }}
                          className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-slate-200 rounded"
                          aria-label="Delete report"
                        >
                          <Trash2 className="h-4 w-4 text-slate-500 hover:text-red-500" />
                        </button>
                      </div>
                      {report.content && (
                        <p className="text-sm text-slate-600 leading-relaxed line-clamp-2">
                          {report.content.substring(0, 150)}...
                        </p>
                      )}
                    </div>
                  )
                })}
              </div>
            </>
          )}

          {activeTab === "snippets" && (
            <>
              {/* Projects List for Snippets */}
              <div className="border-b border-border">
                <div className="flex items-center justify-between px-3 py-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <span>Projects</span>
                    {projects.length > 0 && (
                      <span className="text-xs text-muted-foreground">({projects.length})</span>
                    )}
                  </div>
                </div>

                <div className="space-y-0.5 pb-2">
                  {/* Default project first */}
                  {projects
                    .filter((p) => p.is_default)
                    .map((project) => (
                      <div
                        key={project.id}
                        className={cn(
                          'group relative flex items-start gap-2 px-3 py-2 cursor-pointer transition-colors',
                          'hover:bg-accent/50',
                          snippetProjectId === project.id && 'bg-accent'
                        )}
                        onClick={() => setSnippetProjectId(project.id)}
                      >
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0 mt-1"
                          style={{ backgroundColor: project.color || '#6B7280' }}
                        />
                        <div className="flex-1 min-w-0 pr-16">
                          <div className="text-sm font-medium text-foreground truncate">{project.name}</div>
                          {project.description && (
                            <div className="text-xs text-muted-foreground truncate">{project.description}</div>
                          )}
                        </div>
                        {snippetProjectId === project.id && (
                          <div
                            className={cn(
                              'absolute right-3 top-2 flex items-center justify-center min-w-[44px] h-6 px-2.5 rounded-full text-xs font-medium',
                              'bg-slate-200 text-slate-700'
                            )}
                          >
                            <Code className="h-3 w-3 mr-1" />
                            <span>{snippets.length}</span>
                          </div>
                        )}
                      </div>
                    ))}

                  {/* Other projects */}
                  {projects
                    .filter((p) => !p.is_default)
                    .map((project) => (
                      <div
                        key={project.id}
                        className={cn(
                          'group relative flex items-start gap-2 px-3 py-2 cursor-pointer transition-colors',
                          'hover:bg-accent/50',
                          snippetProjectId === project.id && 'bg-accent'
                        )}
                        onClick={() => setSnippetProjectId(project.id)}
                      >
                        <div
                          className="w-2 h-2 rounded-full flex-shrink-0 mt-1"
                          style={{ backgroundColor: project.color || '#6B7280' }}
                        />
                        <div className="flex-1 min-w-0 pr-10">
                          <div className="text-sm font-medium text-foreground truncate">{project.name}</div>
                          {project.description && (
                            <div className="text-xs text-muted-foreground truncate">{project.description}</div>
                          )}
                        </div>
                        {snippetProjectId === project.id && (
                          <div
                            className={cn(
                              'absolute right-3 top-2 flex items-center justify-center min-w-[44px] h-6 px-2.5 rounded-full text-xs font-medium',
                              'bg-slate-200 text-slate-700'
                            )}
                          >
                            <Code className="h-3 w-3 mr-1" />
                            <span>{snippets.length}</span>
                          </div>
                        )}
                      </div>
                    ))}
                </div>
              </div>

              {/* Snippets List */}
              <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scrollbar-hide">
                {snippetsLoading && snippets.length === 0 && (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                )}

                {snippetsError && (
                  <div className="rounded-xl bg-red-50 border border-red-200 p-4 text-sm text-red-700">
                    {snippetsError}
                  </div>
                )}

                {!snippetsLoading && !snippetsError && snippets.length === 0 && (
                  <div className="text-center py-8">
                    <Code className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
                    <p className="text-sm text-muted-foreground">No snippets yet</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Add code snippets to customize agent behavior
                    </p>
                    {snippetProjectId && (
                      <Button
                        size="sm"
                        className="mt-4"
                        onClick={() => setSnippetModalOpen(true)}
                      >
                        <Plus className="h-4 w-4 mr-1" />
                        Add Snippet
                      </Button>
                    )}
                  </div>
                )}

                {!snippetsLoading && snippets.length > 0 && (
                  <>
                    <div className="flex justify-center mb-3">
                      <Button
                        onClick={() => setSnippetModalOpen(true)}
                        className="w-full justify-center gap-2 h-9 rounded-full bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-500"
                      >
                        <Plus className="h-4 w-4" />
                        <span>Add Snippet</span>
                      </Button>
                    </div>
                    {snippets.map((snippet) => (
                      <div
                        key={snippet.id}
                        className={cn(
                          "rounded-2xl border p-4 transition hover:shadow-sm cursor-pointer",
                          snippet.enabled
                            ? "border-slate-200/80 bg-white/80 hover:border-indigo-200"
                            : "border-slate-200/80 bg-slate-50/50 opacity-60"
                        )}
                        onClick={() => {
                          setSelectedSnippet(snippet)
                          setSnippetPreviewOpen(true)
                        }}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-semibold text-foreground truncate">{snippet.name}</p>
                            <span className="text-xs text-muted-foreground capitalize">
                              {snippet.category.replace('_', ' ')}
                            </span>
                          </div>
                          <span className={cn(
                            "text-xs font-medium px-2 py-0.5 rounded-full flex-shrink-0",
                            snippet.enabled
                              ? "text-green-700 bg-green-100"
                              : "text-slate-600 bg-slate-100"
                          )}>
                            {snippet.enabled ? "Active" : "Disabled"}
                          </span>
                        </div>
                        {snippet.description && (
                          <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                            {snippet.description}
                          </p>
                        )}
                      </div>
                    ))}
                  </>
                )}
              </div>
            </>
          )}

          {activeTab === "databases" && (
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scrollbar-hide">
              {databasesLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : databasesError ? (
                <div className="text-sm text-red-500 text-center py-4">
                  {databasesError}
                </div>
              ) : databases.length === 0 ? (
                <div className="text-sm text-muted-foreground text-center py-4">
                  No databases configured
                </div>
              ) : (
                databases.map((db) => (
                  <button
                    key={db.id}
                    type="button"
                    onClick={() => {
                      setSelectedDatabase(db)
                      setDatabaseModalOpen(true)
                    }}
                    className={cn(
                      "w-full rounded-2xl border p-4 text-left transition hover:shadow-sm",
                      db.is_active
                        ? "border-indigo-200 bg-indigo-50/50 hover:border-indigo-300"
                        : "border-slate-200/80 bg-white/80 hover:border-indigo-200"
                    )}
                  >
                    <div className="flex items-center justify-between gap-3 mb-3">
                      <p className="text-sm font-semibold text-foreground">{db.display_name}</p>
                      <span className={cn(
                        "text-xs font-semibold px-3 py-1 rounded-full whitespace-nowrap",
                        db.is_active
                          ? "text-green-700 bg-green-100"
                          : "text-slate-600 bg-slate-100"
                      )}>
                        {db.is_active ? "Connected" : "Available"}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mb-2">
                      {getDatabaseTypeLabel(db.domain)}
                    </p>
                    <p className="text-sm text-slate-600 leading-relaxed line-clamp-2">{db.description}</p>
                  </button>
                ))
              )}
            </div>
          )}

          <div className="p-4 border-t border-slate-200/80 bg-slate-50/70">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-2xl border border-transparent px-3 py-2 text-left transition hover:border-slate-200 hover:bg-white"
                  aria-label="Open profile menu"
                >
                  <div className="flex flex-col overflow-hidden">
                    <p className="text-sm font-semibold text-foreground truncate">{profileDisplayName}</p>
                    <p className="text-xs text-muted-foreground truncate">{profileSubtext}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" side="right" className="w-56">
                <DropdownMenuLabel>
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-medium">{user?.name}</p>
                    <p className="text-xs text-muted-foreground">{user?.email}</p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => setEditProfileModalOpen(true)}>
                  <User className="mr-2 h-4 w-4" />
                  <span>Edit Profile</span>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleLogout} className="text-red-600 focus:text-red-600">
                  <LogOut className="mr-2 h-4 w-4" />
                  <span>Logout</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </motion.aside>

      {/* Image Lightbox Modal - Rendered via Portal */}
      {lightboxOpen && lightboxImageUrl && createPortal(
        <div 
          className="fixed inset-0 z-[9999] bg-black/90 flex items-center justify-center"
          onClick={() => setLightboxOpen(false)}
        >
          {/* Close button */}
          <button
            className="absolute top-4 right-4 text-white hover:text-gray-300 transition-colors"
            onClick={() => setLightboxOpen(false)}
          >
            <X className="h-8 w-8" />
          </button>

          {/* Image container */}
          <div 
            className="max-w-7xl max-h-[90vh] flex flex-col items-center gap-4 px-16"
            onClick={(e) => e.stopPropagation()}
          >
            <img 
              src={lightboxImageUrl}
              alt={lightboxFilename}
              className="max-w-full max-h-[80vh] object-contain rounded-lg"
            />
            <div className="text-white text-sm bg-black/50 px-4 py-2 rounded-full">
              {lightboxFilename}
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Delete chat?</DialogTitle>
            <DialogDescription>
              This will delete <strong>{conversationToDelete?.title}</strong>.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={handleCancelDelete}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmDelete}
              className="bg-red-600 hover:bg-red-700 text-white"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Report Confirmation Dialog */}
      <Dialog open={deleteReportDialogOpen} onOpenChange={setDeleteReportDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Delete report?</DialogTitle>
            <DialogDescription>
              This will delete the report <strong>{reportToDelete?.title}</strong>.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={handleCancelDeleteReport}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmDeleteReport}
              className="bg-red-600 hover:bg-red-700 text-white"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Report Detail Modal */}
      <ReportDetailModal
        report={selectedReport}
        open={reportModalOpen}
        onClose={handleCloseReportModal}
        onGoToConversation={handleGoToConversation}
      />

      {/* Edit Profile Modal */}
      <EditProfileModal
        open={editProfileModalOpen}
        onOpenChange={setEditProfileModalOpen}
      />

      {/* Database Detail Modal */}
      <DatabaseDetailModal
        database={selectedDatabase}
        open={databaseModalOpen}
        onOpenChange={setDatabaseModalOpen}
      />

      {/* Snippet Manager Modal */}
      {snippetProjectId && (
        <SnippetManagerModal
          open={snippetModalOpen}
          onOpenChange={setSnippetModalOpen}
          project={projects.find(p => p.id === snippetProjectId)!}
        />
      )}

      {/* Snippet Preview Modal */}
      {snippetProjectId && (
        <SnippetPreviewModal
          snippet={selectedSnippet}
          open={snippetPreviewOpen}
          onOpenChange={setSnippetPreviewOpen}
          onEdit={() => {
            setSnippetPreviewOpen(false)
            setSnippetModalOpen(true)
          }}
          onDelete={(snippetId) => {
            deleteSnippet(snippetProjectId, snippetId)
            setSnippetPreviewOpen(false)
          }}
          onToggle={(snippetId) => {
            toggleSnippet(snippetProjectId, snippetId)
          }}
          isLoading={snippetsLoading}
        />
      )}

      {/* Switch Conversation Confirmation Dialog */}
      <SwitchConversationDialog />
    </div>
  )
}

