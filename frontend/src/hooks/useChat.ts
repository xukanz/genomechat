/**
 * Custom hook for real-time chat with SSE streaming
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { useConversationStore } from '../store/conversationStore'
import { useUIStore } from '../store/uiStore'
import { createChatStreamWithFetch, fetchConversationHistory } from '../services/api'
import type { StreamEvent, Plan, AgentActivity } from '../types/conversation'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  thinking?: string
  plan?: Plan
  agentActivities?: AgentActivity[]
  agentResponses?: AgentResponse[]
  files?: FileAttachment[]
  isStreaming?: boolean
  isSummary?: boolean
  timestamp: Date
  agent_name?: string
}

export interface AgentResponse {
  id: string
  agent: string
  content: string
  timestamp: Date
}

export interface FileAttachment {
  id: string
  filename: string
  url: string
  fileType: string
  contentType: string
  isImage: boolean
  agent?: string
  timestamp: Date
}

const AGENT_NAME_MAP: Record<string, string> = {
  coordinator: 'Coordinator',
  orchestrator: 'Orchestrator',
  coder: 'Coder',
  sql_agent: 'SQL Agent',
  sqlagent: 'SQL Agent',
  planner: 'Planner',
  analyst: 'Analyst',
  data_analyst: 'Data Analyst',
  report_writer: 'Report Writer',
}

const isBrowserCryptoAvailable = () => typeof crypto !== 'undefined' && !!crypto.randomUUID

const generateId = () =>
  isBrowserCryptoAvailable() ? crypto.randomUUID() : Math.random().toString(36).slice(2)

const normalizeAgentName = (raw?: unknown) => {
  if (typeof raw !== 'string') return undefined
  const trimmed = raw.trim()
  if (!trimmed) return undefined
  const normalized = trimmed.toLowerCase()
  return normalized.replace(/_reasoning$/, '')
}

const formatAgentLabel = (name: string) =>
  AGENT_NAME_MAP[name] ||
  name
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())

const EXTRACT_TEXT_FIELDS = ['text', 'content', 'response', 'thought', 'reasoning', 'message', 'output']

const extractContent = (content: unknown): string => {
  if (!content) return ''

  if (typeof content === 'string') {
    return content
  }

  if (Array.isArray(content)) {
    return content
      .map((chunk) => extractContent(chunk))
      .filter(Boolean)
      .join('\n')
  }

  if (typeof content === 'object') {
    const record = content as Record<string, unknown>

    if ('type' in record && record.type === 'text' && typeof record.text === 'string') {
      return record.text
    }

    if ('content' in record) {
      const nested = record.content
      const nestedResult = extractContent(nested)
      if (nestedResult) return nestedResult
    }

    if ('messages' in record && Array.isArray(record.messages)) {
      const nestedMessages = (record.messages as unknown[])
        .map((msg) => extractContent(msg))
        .filter(Boolean)
        .join('\n')
      if (nestedMessages) return nestedMessages
    }

    for (const field of EXTRACT_TEXT_FIELDS) {
      if (typeof record[field] === 'string' && record[field]) {
        return record[field] as string
      }
    }

    // As a final fallback, join all string values within the object
    const aggregated = Object.values(record)
      .map((value) => (typeof value === 'string' ? value : ''))
      .filter(Boolean)
      .join('\n')

    return aggregated
  }

  return ''
}

const getAgentNameFromMessage = (msg: any): string | undefined => {
  return (
    normalizeAgentName(msg?.metadata?.agent_name) ||
    normalizeAgentName(msg?.additional_kwargs?.agent_name) ||
    normalizeAgentName(msg?.additional_kwargs?.metadata?.agent_name) ||
    normalizeAgentName(msg?.name)
  )
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentPlan, setCurrentPlan] = useState<Plan | null>(null)
  const suppressHistoryReloadRef = useRef(false)

  // AbortController for cancelling active streams
  const abortControllerRef = useRef<AbortController | null>(null)
  // Track which conversation the current stream belongs to
  const streamConversationRef = useRef<string | null>(null)
  // Track if backend sent explicit 'end' event (vs TCP just closing)
  const receivedEndEventRef = useRef<boolean>(false)

  // Get current conversation ID from store (used in useEffect)
  // For sendMessage, we use getState() to avoid closure issues
  const { currentConversationId, setStreamingState } = useConversationStore()
  const { isDeepResearchEnabled, codeLanguage } = useUIStore()

  // Cancel the current stream
  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      console.log('[useChat] Cancelling active stream')
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      streamConversationRef.current = null
      setIsStreaming(false)
      setStreamingState(false)
    }
  }, [setStreamingState])

  // Cancel stream when conversation changes (user confirmed switch or short stream)
  useEffect(() => {
    // If conversation changed and we have an active stream for a different conversation, cancel it
    if (
      abortControllerRef.current &&
      streamConversationRef.current !== null &&
      streamConversationRef.current !== currentConversationId
    ) {
      console.log('[useChat] Conversation changed, cancelling stream for:', streamConversationRef.current)
      cancelStream()
    }
  }, [currentConversationId, cancelStream])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        console.log('[useChat] Unmounting, cancelling stream')
        abortControllerRef.current.abort()
      }
    }
  }, [])

  // Load conversation history when conversation changes
  useEffect(() => {
    // Clear stale context usage from previous conversation
    useConversationStore.getState().setContextUsage(null)

    if (!currentConversationId) {
      setMessages([])
      setCurrentPlan(null)
      return
    }

    if (suppressHistoryReloadRef.current) {
      suppressHistoryReloadRef.current = false
      return
    }

    const loadHistory = async () => {
      try {
        setIsLoading(true)
        setMessages([]) // Clear old messages immediately to show loading state
        setCurrentPlan(null)
        const history = await fetchConversationHistory(currentConversationId)

        // DEBUG: Log raw history from backend
        console.log('[useChat] Raw history from backend:', JSON.stringify(history, null, 2))

        // Convert backend messages to frontend format retaining agent responses + reasoning
        const convertedMessages: Message[] = []
        let currentAssistant: Message | null = null
        let assistantIndex = 0

        const ensureAssistant = (timestamp: Date) => {
          if (!currentAssistant) {
            currentAssistant = {
              id: `${history.id}-assistant-${assistantIndex++}`,
              role: 'assistant',
              content: '',
              thinking: '',
              agentResponses: [],
              timestamp,
            }
          }
          return currentAssistant
        }

        const commitAssistant = () => {
          if (!currentAssistant) return

          const { content, thinking, agentResponses, files } = currentAssistant
          const hasContent = Boolean(content?.trim())
          const hasThinking = Boolean(thinking?.trim())
          const hasResponses = Boolean(agentResponses && agentResponses.length)
          const hasFiles = Boolean(files && files.length)

          // Commit if there's any content, thinking, responses, OR files
          if (hasContent || hasThinking || hasResponses || hasFiles) {
            convertedMessages.push({
              ...currentAssistant,
              content: hasContent ? (content || '').trim() : '',
              thinking: hasThinking ? thinking?.trim() : undefined,
              agentResponses: hasResponses ? agentResponses : undefined,
              files: hasFiles ? files : undefined,
            })
          }

          currentAssistant = null
        }

        const workerAgents = new Set(['coder', 'sql_agent', 'sqlagent', 'data_analyst', 'analyst'])

        const hasUpcomingWorkerMessage = (startIdx: number) => {
          for (let i = startIdx + 1; i < history.messages.length; i += 1) {
            const nextMsg = history.messages[i]
            if (!nextMsg) continue

            if (nextMsg.type === 'human') {
              const nextAgent = getAgentNameFromMessage(nextMsg)
              if (!nextAgent) {
                return false
              }
              if (workerAgents.has(nextAgent)) {
                return true
              }
            }

            if (nextMsg.type === 'ai' || nextMsg.type === 'system') {
              continue
            }
          }
          return false
        }

        let conversationSummary: string | null = null

        history.messages.forEach((msg: any, idx: number) => {
          const content = extractContent(msg.content)
          const timestamp = new Date()

          // Debug: Log messages with files
          if (msg.files && msg.files.length > 0) {
            console.log('[useChat] Message with files:', {
              type: msg.type,
              name: msg.name,
              filesCount: msg.files.length,
              files: msg.files
            })
          }

          if (msg.type === 'system') {
            // Detect summarization middleware output
            if (content.includes('Previous conversation summary') ||
                content.includes('[Conversation Summary]')) {
              conversationSummary = content
              return
            }

            const agentName = getAgentNameFromMessage(msg) || normalizeAgentName(msg.name)
            if (content.trim()) {
              const assistant = ensureAssistant(timestamp)
              const label = formatAgentLabel(agentName || 'Thought')
              assistant.thinking = assistant.thinking
                ? `${assistant.thinking}\n${label}: ${content.trim()}`
                : `${label}: ${content.trim()}`
            }
            return
          }

          if (msg.type === 'human') {
            const agentName = getAgentNameFromMessage(msg)

            if (!agentName) {
              commitAssistant()
              convertedMessages.push({
                id: `${history.id}-user-${idx}`,
                role: 'user',
                content,
                timestamp,
              })
              return
            }

            if (content.trim()) {
              const assistant = ensureAssistant(timestamp)
              const label = formatAgentLabel(agentName)
              const responses = assistant.agentResponses || []
              // Always append new responses to show multiple responses from same agent
              responses.push({
                id: generateId(),
                agent: label,
                content,
                timestamp,
              })
              assistant.agentResponses = responses
            }
            return
          }

          if (msg.type === 'ai') {
            const agentName = getAgentNameFromMessage(msg)
            const isOrchestrator = agentName === 'orchestrator'

            console.log('[useChat] Processing AI message:', {
              type: msg.type,
              name: agentName,
              hasFiles: msg.files?.length || 0,
              isOrchestrator,
              hasUpcoming: isOrchestrator && hasUpcomingWorkerMessage(idx)
            })

            // IMPORTANT: Always process files first, before any early returns
            // Files can be attached to any AI message, including intermediate orchestrator messages
            if (msg.files && msg.files.length > 0) {
              const assistant = ensureAssistant(timestamp)
              const existingIds = new Set(assistant.files?.map((f: FileAttachment) => f.id) || [])
              const newFiles = msg.files.filter((f: FileAttachment) => !existingIds.has(f.id))
              if (newFiles.length > 0) {
                console.log('[useChat] Attaching files to assistant:', newFiles.length, 'new files (filtered from', msg.files.length, ')')
                assistant.files = [...(assistant.files || []), ...newFiles]
              }
            }

            // Orchestrator routing messages go to thinking (not main content)
            if (isOrchestrator && hasUpcomingWorkerMessage(idx)) {
              if (content.trim()) {
                const assistant = ensureAssistant(timestamp)
                const label = formatAgentLabel(agentName)
                assistant.thinking = assistant.thinking
                  ? `${assistant.thinking}\n${label}: ${content.trim()}`
                  : `${label}: ${content.trim()}`
              }
              return
            }

            // Process content for final AI messages
            if (content.trim()) {
              const assistant = ensureAssistant(timestamp)
              assistant.content = assistant.content
                ? `${assistant.content}\n\n${content.trim()}`
                : content.trim()
            }
            return
          }
        })

        commitAssistant()

        // Insert summary banner at top if conversation was summarized
        if (conversationSummary) {
          convertedMessages.unshift({
            id: `${history.id}-summary`,
            role: 'system' as const,
            content: conversationSummary,
            isSummary: true,
            timestamp: new Date(),
          })
        }

        setMessages(convertedMessages)

        // Restore context usage from history response
        if (history.token_usage) {
          useConversationStore.getState().setContextUsage(history.token_usage)
        }

        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load conversation history')
        console.error('Failed to load conversation history:', err)
      } finally {
        setIsLoading(false)
      }
    }

    loadHistory()
  }, [currentConversationId])

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return

      // CRITICAL: Get current conversation ID directly from store to avoid closure issues
      const currentThreadId = useConversationStore.getState().currentConversationId

      // Cancel any existing stream before starting new one
      if (abortControllerRef.current) {
        console.log('[useChat] Cancelling previous stream before new message')
        abortControllerRef.current.abort()
      }

      // Create new AbortController for this request
      abortControllerRef.current = new AbortController()
      // Track which conversation this stream belongs to
      streamConversationRef.current = currentThreadId

      // Add user message to UI
      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, userMessage])

      // Create placeholder assistant message
      const assistantId = crypto.randomUUID()
      const assistantMessage: Message = {
        id: assistantId,
        role: 'assistant',
        content: '',
        thinking: '',
        plan: undefined,
        agentActivities: [],
        agentResponses: [],
        isStreaming: true,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, assistantMessage])
      setCurrentPlan(null)

      setIsStreaming(true)
      setError(null)
      // Reset end event tracking for new stream
      receivedEndEventRef.current = false
      // Update store streaming state for confirmation dialog logic
      setStreamingState(true, isDeepResearchEnabled)

      try {
        // Get selected project ID from project store
        const { useProjectStore } = await import('../store/projectStore')
        const selectedProjectId = useProjectStore.getState().selectedProjectId

        // Get active database from database store
        const { useDatabaseStore } = await import('../store/databaseStore')
        const activeDatabase = useDatabaseStore.getState().activeDatabase

        await createChatStreamWithFetch(
          {
            message: content,
            thread_id: currentThreadId,  // Use fresh value from store
            project_id: selectedProjectId || undefined,  // Pass selected project
            research_mode: isDeepResearchEnabled ? 'deep_research' : 'standard',
            code_language: codeLanguage,
            database_id: activeDatabase || undefined,  // Pass active database
          },
          (event: StreamEvent) => {
            // Handle different event types
            if (event.type === 'token') {
              // Append streaming tokens to assistant message
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? { ...msg, content: msg.content + event.content }
                    : msg
                )
              )
            } else if (event.type === 'thinking' || event.type === 'agent_start') {
              // Update thinking process
              const thinkingContent = event.agent_name
                ? `${event.agent_name}: ${event.content}`
                : event.content
              setMessages((prev) =>
                prev.map((msg) => {
                  if (msg.id !== assistantId) return msg
                  
                  const updatedMsg = {
                    ...msg,
                    thinking: (msg.thinking || '') + thinkingContent + '\n'
                  }
                  
                  // If agent_start, also add to agent activities AND update plan
                  if (event.type === 'agent_start' && event.agent_name) {
                    const agentExists = msg.agentActivities?.some(a => a.agent === event.agent_name && !a.endTime)
                    if (!agentExists) {
                      updatedMsg.agentActivities = [
                        ...(msg.agentActivities || []),
                        {
                          agent: event.agent_name,
                          status: 'working',
                          startTime: new Date(),
                        }
                      ]
                    }
                    
                    // Update corresponding plan step to in_progress
                    if (updatedMsg.plan?.steps) {
                      updatedMsg.plan = {
                        ...updatedMsg.plan,
                        steps: updatedMsg.plan.steps.map(step =>
                          step.agent_name === event.agent_name && step.status === 'pending'
                            ? { ...step, status: 'in_progress' }
                            : step
                        )
                      }
                    }
                  }
                  
                  return updatedMsg
                })
              )
            } else if (event.type === 'agent_end') {
              // Mark agent as completed in activities AND update plan
              setMessages((prev) =>
                prev.map((msg) => {
                  if (msg.id !== assistantId) return msg
                  
                  const agentName = event.agent_name || 'Assistant'
                  const updatedActivities = (msg.agentActivities || []).map(activity =>
                    activity.agent === agentName && !activity.endTime
                      ? {
                          ...activity,
                          status: 'completed' as const,
                          content: event.content,
                          endTime: new Date(),
                        }
                      : activity
                  )
                  
                  let updatedPlan = msg.plan
                  if (updatedPlan?.steps) {
                    updatedPlan = {
                      ...updatedPlan,
                      steps: updatedPlan.steps.map(step =>
                        step.agent_name === event.agent_name && step.status === 'in_progress'
                          ? { ...step, status: 'completed' as const }
                          : step
                      )
                    }
                  }

                  const existingResponses = msg.agentResponses || []
                  let nextResponses = existingResponses

                  if ((event.content || '').trim()) {
                    // Always append new responses to show multiple responses from same agent
                    nextResponses = [
                      ...existingResponses,
                      {
                        id: crypto.randomUUID(),
                        agent: agentName,
                        content: event.content,
                        timestamp: new Date(),
                      },
                    ]
                  }
                  
                  return {
                    ...msg,
                    agentActivities: updatedActivities,
                    plan: updatedPlan,
                    agentResponses: nextResponses,
                  }
                })
              )
            } else if (event.type === 'plan') {
              // Parse and update plan in UI (merge to preserve status updates)
              try {
                const newPlanData: Plan = JSON.parse(event.content)
                setMessages((prev) =>
                  prev.map((msg) => {
                    if (msg.id !== assistantId) return msg
                    
                    // Merge new plan with existing plan to preserve status updates
                    const mergedPlan = msg.plan ? {
                      ...newPlanData,
                      steps: newPlanData.steps.map((newStep, idx) => {
                        const existingStep = msg.plan?.steps[idx]
                        // If step exists and has a more advanced status, keep it
                        if (existingStep) {
                          const statusPriority = { pending: 0, in_progress: 1, completed: 2, failed: 2 }
                          const existingPriority = statusPriority[existingStep.status] || 0
                          const newPriority = statusPriority[newStep.status] || 0
                          return existingPriority >= newPriority ? existingStep : newStep
                        }
                        return newStep
                      })
                    } : newPlanData
                    
                    setCurrentPlan(mergedPlan)
                    return { ...msg, plan: mergedPlan }
                  })
                )
              } catch (err) {
                console.error('Failed to parse plan data:', err)
              }
            } else if (event.type === 'file' && event.file_metadata) {
              // Add file attachment to message
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,
                        files: [
                          ...(msg.files || []),
                          {
                            id: crypto.randomUUID(),
                            filename: event.file_metadata!.filename,
                            url: event.file_metadata!.url,
                            fileType: event.file_metadata!.file_type,
                            contentType: event.file_metadata!.content_type,
                            isImage: event.file_metadata!.is_image,
                            agent: event.agent_name,
                            timestamp: new Date(),
                          }
                        ]
                      }
                    : msg
                )
              )
            } else if (event.type === 'error') {
              setError(event.content)
            } else if (event.type === 'end') {
              // Stream completed - mark explicit end received
              receivedEndEventRef.current = true
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId ? { ...msg, isStreaming: false } : msg
                )
              )
              setIsStreaming(false)
              setStreamingState(false)
              abortControllerRef.current = null
              streamConversationRef.current = null

              // CRITICAL: If this was a new conversation, set it as current
              // This matches the CLI behavior where thread_id is stored and reused
              // Use getState() to avoid closure issues and get fresh store reference
              // Update context usage from end event
              if (event.token_usage) {
                useConversationStore.getState().setContextUsage(event.token_usage)
              }

              const storeState = useConversationStore.getState()
              if (!storeState.currentConversationId && event.thread_id) {
                console.log('[useChat] Setting new conversation ID:', event.thread_id)

                // Set as current conversation immediately for continuity
                suppressHistoryReloadRef.current = true
                // Update stream ref to match new conversation
                streamConversationRef.current = event.thread_id
                storeState.setCurrentConversation(event.thread_id)

                // Refresh conversation list to show new conversation in sidebar
                storeState.loadConversations()
              }
            }
          },
          (err: Error) => {
            // Don't show error for AbortError - it's expected when cancelling
            if (err.name !== 'AbortError') {
              setError(err.message)
            }
            setIsStreaming(false)
            setStreamingState(false)
            abortControllerRef.current = null
            streamConversationRef.current = null
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId ? { ...msg, isStreaming: false } : msg
              )
            )
          },
          () => {
            // TCP stream closed - only reset state if we received explicit 'end' event
            // This prevents premature state reset if TCP closes before backend finishes
            if (receivedEndEventRef.current) {
              // Normal completion - state already handled by 'end' event handler
              return
            }

            // TCP closed without 'end' event - add fallback timeout
            console.log('[useChat] TCP closed without explicit end event, waiting...')
            setTimeout(() => {
              // Only reset if still no 'end' event received
              if (!receivedEndEventRef.current) {
                console.log('[useChat] Fallback timeout: resetting streaming state')
                setIsStreaming(false)
                setStreamingState(false)
                abortControllerRef.current = null
                streamConversationRef.current = null
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantId ? { ...msg, isStreaming: false } : msg
                  )
                )
              }
            }, 5000) // 5-second fallback timeout
          },
          abortControllerRef.current.signal  // Pass AbortSignal
        )
      } catch (err) {
        // Don't show error for AbortError
        if (err instanceof Error && err.name !== 'AbortError') {
          setError(err.message)
        } else if (!(err instanceof Error)) {
          setError('Failed to send message')
        }
        setIsStreaming(false)
        setStreamingState(false)
        abortControllerRef.current = null
        streamConversationRef.current = null
      }
    },
    [isDeepResearchEnabled, codeLanguage, setStreamingState]
  )

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  return {
    messages,
    isLoading,
    isStreaming,
    error,
    currentPlan,
    sendMessage,
    clearError,
    cancelStream,
  }
}
