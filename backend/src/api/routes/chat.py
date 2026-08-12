"""Chat endpoints for streaming and non-streaming responses."""

import asyncio
import functools
import logging
import re
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage  # noqa: F401 - Used in generator

from langchain.agents.middleware.summarization import count_tokens_approximately

from src.models.api import ChatRequest, ChatResponse, StreamEvent
from src.models.user import User
from src.agent import graph_builder
from src.config.settings import settings
from src.graph.checkpointer import create_checkpointer
from src.service.auth.dependencies import get_optional_user
from src.service.observability import (
    build_request_trace_attrs,
    build_request_trace_finalize_attrs,
    tracer,
)
from src.utils.context import database_id_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@functools.lru_cache(maxsize=1)
def _pilot_user_ids_set() -> frozenset[str]:
    """Parse settings.memory_pilot_user_ids once per process. Call is cheap on cache hit."""
    raw = settings.memory_pilot_user_ids or ""
    return frozenset(s.strip() for s in raw.split(",") if s.strip())


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    user: User | None = Depends(get_optional_user),
) -> ChatResponse:
    """Synchronous chat endpoint.

    Processes a user message and returns the complete response.

    Args:
        request: Chat request with message and optional thread_id

    Returns:
        Chat response with assistant message and thread_id

    Raises:
        HTTPException: If agent invocation fails
    """
    try:
        # Extract user_id from optional authentication
        user_id = user.id if user else None

        # Generate conversation_id if not provided
        conversation_id = request.thread_id or str(uuid.uuid4())

        # Generate thread_id in format: {user_id}:{conversation_id}
        if user_id:
            thread_id = f"{user_id}:{conversation_id}"
        else:
            thread_id = f"anonymous:{conversation_id}"

        # Phase 2 Workstream C — request-scoped root trace span. Mirrors
        # stream_chat so non-streaming requests are grouped into a single
        # Langfuse trace with the same session/user metadata.
        trace_attrs = build_request_trace_attrs(
            user_id=user_id,
            thread_id=thread_id,
            first_user_message=request.message,
            research_mode=request.research_mode,
            code_language=request.code_language,
            database_id=request.database_id,
        )
        with tracer.start_as_current_span("agent.request", attributes=trace_attrs) as _request_span:
            # Create/update conversation metadata in MongoDB
            from src.service.storage.conversation_service import ConversationService

            conversation_service = ConversationService()
            # Bound before the try so a metadata failure degrades to "don't
            # generate a title" rather than raising NameError below. Defaulting
            # to False also stops a failed lookup from being read as a new
            # conversation, which would regenerate an existing title.
            is_new_conversation = False
            try:
                # Try to get existing conversation
                conversation = conversation_service.get_conversation(
                    conversation_id, user_id or "anonymous"
                )
                if conversation:
                    # Update timestamp
                    conversation_service.update_timestamp(conversation_id, user_id or "anonymous")
                    logger.debug(f"Found existing conversation: {conversation_id}")
                else:
                    # Create new conversation with title from first message
                    title = request.message[:100]  # Use first 100 chars as title
                    conversation_service.create_conversation(
                        conversation_id,
                        user_id or "anonymous",
                        title,
                        project_id=request.project_id,  # Use project_id from request
                    )
                    is_new_conversation = True
                    logger.info(
                        f"✨ Created new conversation {conversation_id} in project {request.project_id or 'default'}"
                    )
            except Exception as e:
                logger.warning(f"Failed to manage conversation metadata: {e}")

            # Configure agent with thread_id for state persistence
            config = {"configurable": {"thread_id": thread_id}}

            # Set database context from request (for request-scoped database selection)
            if request.database_id:
                database_id_context.set(request.database_id)
                logger.info(f"Set database context to: {request.database_id}")

            # Create checkpointer per-request (supports MongoDB and SQLite)
            async with create_checkpointer() as checkpointer:
                # Compile graph with fresh checkpointer for this request
                agent = graph_builder.compile(checkpointer=checkpointer)

                # Invoke agent with user message, research_mode, code_language, thread_id, project_id, and database_id
                result = await agent.ainvoke(
                    {
                        "messages": [HumanMessage(content=request.message)],
                        "research_mode": request.research_mode,
                        "code_language": request.code_language,
                        "thread_id": thread_id,  # Add thread_id to state for tools to access
                        "project_id": request.project_id,  # Add project_id for snippet injection
                        "database_id": request.database_id,  # Add database_id for database context
                    },
                    config=config,
                )

            # Extract assistant's response
            assistant_message = result["messages"][-1].content

            # Finalize the request trace span with output text + tags. Mirrors
            # the streaming path so Langfuse populates Input/Output identically.
            try:
                existing_tags: list[str] | None = None
                try:
                    open_attrs = getattr(_request_span, "attributes", None)
                    if open_attrs is not None:
                        raw = open_attrs.get("langfuse.tags")
                        if raw is not None:
                            existing_tags = list(raw)
                except Exception:  # noqa: BLE001
                    existing_tags = None

                finalize_attrs = build_request_trace_finalize_attrs(
                    first_user_message=request.message,
                    output=str(assistant_message) if assistant_message else "",
                    turn_index=None,
                    existing_tags=existing_tags,
                    research_mode=request.research_mode,
                )
                if finalize_attrs:
                    _request_span.set_attributes(finalize_attrs)
            except Exception as _e:  # noqa: BLE001
                logger.debug("failed to finalize trace attrs (sync): %s", _e)

            # Auto-generate title for first message in conversation (async, non-blocking)
            if is_new_conversation:
                logger.info(
                    f"🎯 Scheduling title generation for new conversation {conversation_id}"
                )
                # Run title generation in background without blocking response
                background_tasks.add_task(
                    conversation_service.auto_generate_and_update_title,
                    conversation_id=conversation_id,
                    user_id=user_id or "anonymous",
                    user_message=request.message,
                    assistant_message=assistant_message,
                )

            return ChatResponse(message=assistant_message, thread_id=conversation_id)

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    user: User | None = Depends(get_optional_user),
) -> StreamingResponse:
    """Streaming chat endpoint using Server-Sent Events (SSE).

    Streams the assistant's response token by token in real-time.
    Also streams plan events when manage_plan tool updates the plan.

    Args:
        request: Chat request with message and optional thread_id

    Returns:
        StreamingResponse with SSE events
    """

    async def event_generator() -> AsyncIterator[str]:
        """Generate SSE events for streaming response.

        Yields:
            SSE formatted strings with token and plan data
        """
        # Compute request-identity fields BEFORE opening the trace span so
        # they can flow into its attributes. These are the same values the
        # existing generator body uses — no behavior change.
        user_id = user.id if user else None
        conversation_id = request.thread_id or str(uuid.uuid4())
        thread_id = f"{user_id}:{conversation_id}" if user_id else f"anonymous:{conversation_id}"

        # Phase 2 Workstream C — request-scoped root trace span.
        # All downstream @trace_node / @trace_tool / gen_ai.chat spans nest
        # under this one, so Langfuse can group them into a single trace
        # and attach session/user/tag metadata at the trace level.
        # Safe to emit unconditionally: when otel_enabled=False the tracer
        # is a no-op, and build_request_trace_attrs returns {} so the
        # attribute set is empty.
        trace_attrs = build_request_trace_attrs(
            user_id=user_id,
            thread_id=thread_id,
            first_user_message=request.message,
            research_mode=request.research_mode,
            code_language=request.code_language,
            database_id=request.database_id,
        )
        with tracer.start_as_current_span("agent.request", attributes=trace_attrs) as _request_span:
            try:
                # Create/update conversation metadata in MongoDB
                from src.service.storage.conversation_service import ConversationService

                conversation_service = ConversationService()
                is_new_conversation = False
                try:
                    # Try to get existing conversation
                    conversation = conversation_service.get_conversation(
                        conversation_id, user_id or "anonymous"
                    )
                    if conversation:
                        # Update timestamp
                        conversation_service.update_timestamp(
                            conversation_id, user_id or "anonymous"
                        )
                        logger.debug(f"Found existing conversation: {conversation_id}")
                    else:
                        # Create new conversation with temporary title
                        title = request.message[:100]  # Temporary title, will be auto-generated
                        conversation_service.create_conversation(
                            conversation_id,
                            user_id or "anonymous",
                            title,
                            project_id=request.project_id,  # Use project_id from request
                        )
                        is_new_conversation = True
                        logger.info(
                            f"✨ Created new conversation {conversation_id} in project {request.project_id or 'default'}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to manage conversation metadata: {e}")

                # Configure agent with thread_id
                config = {"configurable": {"thread_id": thread_id}}

                # Set database context from request (for request-scoped database selection)
                if request.database_id:
                    database_id_context.set(request.database_id)
                    logger.info(f"Set database context to: {request.database_id}")

                logger.info(f"Starting stream for conversation: {conversation_id}")

                # Emit thinking event to show agent is processing
                thinking_event = StreamEvent(
                    type="thinking",
                    content="Processing your request...",
                    thread_id=conversation_id,
                )
                yield f"data: {thinking_event.model_dump_json()}\n\n"

                # Create checkpointer per-request (supports MongoDB and SQLite)
                async with create_checkpointer() as checkpointer:
                    # Compile graph with fresh checkpointer for this request
                    agent = graph_builder.compile(checkpointer=checkpointer)

                    # Track tool results that contain images
                    tool_images = []

                    # Track emitted orchestrator task instructions to prevent duplicates
                    # Key: (worker_node_name, orchestrator_task_content_hash)
                    emitted_orchestrator_tasks = set()

                    # Track emitted agent_start events to prevent duplicates
                    # Key: node_name (since on_chain_start can fire multiple times for subgraphs)
                    emitted_agent_starts = set()

                    # Track full assistant message for auto-title generation
                    full_assistant_message = []

                    # CRITICAL: Use astream_events with version="v2" for token streaming
                    async for event in agent.astream_events(
                        {
                            "messages": [HumanMessage(content=request.message)],
                            "research_mode": request.research_mode,
                            "code_language": request.code_language,
                            "thread_id": thread_id,  # Add thread_id to state for tools to access
                            "project_id": request.project_id,  # Add project_id for snippet injection
                            "database_id": request.database_id,  # Add database_id for database context
                        },
                        config=config,
                        version="v2",
                    ):
                        event_name = event.get("event", "")
                        event_node_name = event.get("name", "")

                        # Also check metadata for node name (LangGraph may store it there)
                        metadata = event.get("metadata", {})
                        checkpoint_ns = metadata.get("checkpoint_ns", "")
                        # Extract node name from checkpoint namespace if present (format: "node_name:step_id")
                        if checkpoint_ns and ":" in checkpoint_ns:
                            node_from_metadata = checkpoint_ns.split(":")[0]
                        else:
                            node_from_metadata = None

                        # Use node name from event name or metadata
                        # Try event name first, then metadata
                        node_name = event_node_name or node_from_metadata
                        # Normalize to lowercase for comparison (agent_name_map uses lowercase keys)
                        if node_name:
                            node_name = node_name.lower()

                        # Map node names to friendly agent names (only top-level graph nodes)
                        # Subgraph internal nodes (like sql_agent subgraph nodes) are filtered out
                        agent_name_map = {
                            "coordinator": "Coordinator",
                            "orchestrator": "Orchestrator",
                            "coder": "Coder",
                            "sql_agent": "SQL Agent",
                        }

                        # Filter: Only process top-level graph nodes, ignore subgraph internal nodes
                        # Top-level nodes: coordinator, orchestrator, coder, sql_agent
                        # Subgraph internal nodes have different names (e.g., process_agent_result, validate_sql)
                        is_top_level_node = node_name in agent_name_map

                        worker_nodes = ["sql_agent", "coder"]

                        # Emit agent_start when worker nodes START
                        # This provides observability: agent_start → agent_end → show response
                        if event_name == "on_chain_start" and node_name in worker_nodes:
                            # Deduplicate: Check if we've already emitted agent_start for this node
                            # on_chain_start can fire multiple times (e.g., subgraph entry and node start)
                            if node_name in emitted_agent_starts:
                                logger.debug(f"Skipping duplicate agent_start for {node_name}")
                                continue

                            agent_name = agent_name_map[node_name]
                            logger.info(f"Agent {agent_name} started")

                            # Emit orchestrator task instruction first (if available)
                            event_data = event.get("data", {})
                            state = event_data.get("input") or event_data.get("snapshot", {})

                            if isinstance(state, dict) and "messages" in state:
                                messages = state["messages"]

                                # Find the most recent orchestrator message (AIMessage with name="orchestrator")
                                # This is the task instruction for this worker
                                from langchain_core.messages import AIMessage
                                import hashlib

                                orchestrator_task = None
                                for msg in reversed(messages):
                                    if (
                                        isinstance(msg, AIMessage)
                                        and hasattr(msg, "name")
                                        and msg.name == "orchestrator"
                                    ):
                                        orchestrator_task = msg.content
                                        break

                                if orchestrator_task:
                                    # Deduplicate: Check if we've already emitted this orchestrator task for this worker
                                    task_hash = hashlib.md5(orchestrator_task.encode()).hexdigest()
                                    dedup_key = (node_name, task_hash)

                                    if dedup_key not in emitted_orchestrator_tasks:
                                        # Emit orchestrator's task instruction as thinking event
                                        # This shows what task is being sent to the worker, right before it starts
                                        thinking_event = StreamEvent(
                                            type="thinking",
                                            content=orchestrator_task,
                                            thread_id=conversation_id,
                                            agent_name="Orchestrator",
                                        )
                                        yield f"data: {thinking_event.model_dump_json()}\n\n"
                                        emitted_orchestrator_tasks.add(dedup_key)
                                        logger.info(
                                            f"Emitted Orchestrator task instruction (thinking event) - task for {agent_name}"
                                        )

                            # Emit agent_start event
                            start_event = StreamEvent(
                                type="agent_start",
                                content=f"{agent_name} started",
                                thread_id=conversation_id,
                                agent_name=agent_name,
                            )
                            yield f"data: {start_event.model_dump_json()}\n\n"
                            logger.info(f"Emitted {agent_name} start event")

                            # Mark as emitted to prevent duplicates
                            emitted_agent_starts.add(node_name)

                        # Track agent end events (when nodes finish processing)
                        if event_name == "on_chain_end" and is_top_level_node:
                            agent_name = agent_name_map[node_name]

                            # Extract output from event
                            from langgraph.types import Command

                            output = event.get("data", {}).get("output", None)

                            # Debug orchestrator output
                            if node_name == "orchestrator":
                                logger.info("🔍 Orchestrator on_chain_end event:")
                                logger.info(f"   output type: {type(output)}")
                                logger.info(f"   is Command: {isinstance(output, Command)}")
                                if isinstance(output, Command):
                                    logger.info(
                                        f"   Command.update type: {type(output.update) if output.update else 'None'}"
                                    )
                                    logger.info(
                                        f"   Command.update keys: {list(output.update.keys()) if output.update else 'None'}"
                                    )
                                    if output.update and "plan" in output.update:
                                        plan_obj = output.update["plan"]
                                        logger.info("   ✅ Plan found in Command.update!")
                                        logger.info(f"   Plan type: {type(plan_obj)}")
                                        logger.info(
                                            f"   Plan.steps count: {len(plan_obj.steps) if hasattr(plan_obj, 'steps') else 'N/A'}"
                                        )
                                    else:
                                        logger.warning("   ⚠️  No 'plan' key in Command.update")

                            # Plan emission is handled later from snapshot (after all processing)
                            # This avoids duplicate emissions and ensures we always have the latest plan state
                            # Note: Removed duplicate plan emission from here - now only emitted from snapshot below

                            # For worker nodes, emit agent_end with complete response
                            if node_name in worker_nodes:
                                logger.info(f"Agent {agent_name} finished")

                                # Extract complete response from output
                                from langgraph.types import Command

                                output = event.get("data", {}).get("output", None)

                                worker_response = ""
                                if (
                                    isinstance(output, Command)
                                    and output.update
                                    and "messages" in output.update
                                ):
                                    messages = output.update["messages"]

                                    # Find the worker's response (HumanMessage with name matching the node)
                                    for msg in reversed(messages):
                                        if (
                                            isinstance(msg, HumanMessage)
                                            and hasattr(msg, "name")
                                            and msg.name == node_name
                                        ):
                                            worker_response = msg.content

                                            # Extract content from RESPONSE_FORMAT wrapper if present
                                            if (
                                                "<response>" in worker_response
                                                and "</response>" in worker_response
                                            ):
                                                start = worker_response.index("<response>") + len(
                                                    "<response>"
                                                )
                                                end = worker_response.index("</response>")
                                                worker_response = worker_response[start:end].strip()
                                            break

                                # Emit agent_end event with complete response
                                end_event = StreamEvent(
                                    type="agent_end",
                                    content=worker_response,
                                    thread_id=conversation_id,
                                    agent_name=agent_name,
                                )
                                yield f"data: {end_event.model_dump_json()}\n\n"
                                logger.info(
                                    f"Emitted {agent_name} end event with {len(worker_response)} chars"
                                )
                                continue

                            logger.debug(
                                f"Stream: Processing on_chain_end event for {agent_name} (node: {node_name})"
                            )

                            # Extract agent output from the event data
                            from langgraph.types import Command

                            output = event.get("data", {}).get("output", None)

                            logger.debug(
                                f"Stream: Output type: {type(output)}, is Command: {isinstance(output, Command)}"
                            )

                            # Extract messages from Command output (nodes return Command objects)
                            if (
                                isinstance(output, Command)
                                and output.update
                                and "messages" in output.update
                            ):
                                messages = output.update["messages"]
                                logger.debug(
                                    f"Stream: Found {len(messages)} message(s) in Command output for {agent_name}"
                                )

                                # Process messages in order: reasoning first (thinking), then response (token)
                                for idx, message in enumerate(messages):
                                    logger.debug(
                                        f"Stream: Processing message {idx + 1}/{len(messages)} for {agent_name}, type: {type(message).__name__}"
                                    )

                                    if not hasattr(message, "content") or not message.content:
                                        logger.debug(
                                            f"Stream: Message {idx + 1} has no content, skipping"
                                        )
                                        continue

                                    logger.debug(
                                        f"Stream: Message {idx + 1} content length: {len(message.content)}, preview: {message.content[:100]}"
                                    )

                                    # Check for coordinator reasoning (SystemMessage with name="coordinator_reasoning")
                                    # Emit as "thinking" event to show inner thought
                                    from langchain_core.messages import SystemMessage, AIMessage

                                    if (
                                        isinstance(message, SystemMessage)
                                        and hasattr(message, "name")
                                        and message.name == "coordinator_reasoning"
                                    ):
                                        thinking_event = StreamEvent(
                                            type="thinking",
                                            content=message.content,
                                            thread_id=conversation_id,
                                            agent_name=agent_name,
                                        )
                                        yield f"data: {thinking_event.model_dump_json()}\n\n"
                                        logger.info(
                                            f"Emitted {agent_name} reasoning (thinking event)"
                                        )
                                        continue

                                    # For Orchestrator: skip routing messages to workers (already emitted when worker starts)
                                    # Only emit final responses when routing to __end__
                                    if node_name == "orchestrator" and isinstance(
                                        message, AIMessage
                                    ):
                                        # Check if orchestrator is routing to a worker (not __end__)
                                        # The Command's goto field tells us where it's routing
                                        is_routing_to_worker = (
                                            isinstance(output, Command)
                                            and output.goto
                                            and output.goto != "__end__"
                                        )

                                        if is_routing_to_worker:
                                            # Skip routing messages to workers - already shown as thinking when worker starts
                                            # This prevents duplication and ensures correct chronological order
                                            logger.debug(
                                                f"Skipping orchestrator routing message to {output.goto} - will be shown when worker starts"
                                            )
                                            continue

                                        # Continue to emit token events for final responses (when routing to __end__)
                                        # (when routing to __end__, this shows final_response)

                                    # Check for response content (HumanMessage or other message types)
                                    # Emit as "token" event for the actual answer
                                    agent_output_content = message.content

                                    # Extract content from RESPONSE_FORMAT wrapper if present
                                    # Format: "Response from {agent}:\n\n<response>\n{content}\n</response>\n\n*Please execute the next step.*"
                                    if (
                                        "<response>" in agent_output_content
                                        and "</response>" in agent_output_content
                                    ):
                                        start = agent_output_content.index("<response>") + len(
                                            "<response>"
                                        )
                                        end = agent_output_content.index("</response>")
                                        agent_output_content = agent_output_content[
                                            start:end
                                        ].strip()
                                        logger.debug(
                                            f"Stream: Extracted content from RESPONSE_FORMAT wrapper, new length: {len(agent_output_content)}"
                                        )

                                    # Skip empty or very short content (might be intermediate messages)
                                    if len(agent_output_content.strip()) < 3:
                                        logger.debug(
                                            f"Stream: Skipping message {idx + 1} for {agent_name} - content too short ({len(agent_output_content.strip())} chars)"
                                        )
                                        continue

                                    logger.debug(
                                        f"Stream: Emitting {agent_name} output event with {len(agent_output_content)} chars"
                                    )

                                    # Emit agent output as token events (for non-streaming agents)
                                    # Stream it progressively by chunking to simulate real-time streaming
                                    # Chunk the content and stream it progressively
                                    chunk_size = 50  # Characters per chunk for smooth streaming
                                    for i in range(0, len(agent_output_content), chunk_size):
                                        chunk = agent_output_content[i : i + chunk_size]
                                        stream_event = StreamEvent(
                                            type="token",
                                            content=chunk,
                                            thread_id=conversation_id,
                                            agent_name=agent_name,
                                        )
                                        yield f"data: {stream_event.model_dump_json()}\n\n"
                                        # Small delay to simulate streaming (5ms per chunk)
                                        await asyncio.sleep(0.005)
                                    logger.info(
                                        f"Emitted {agent_name} output event ({len(agent_output_content)} chars in chunks)"
                                    )
                                    # Track for auto-title generation fallback
                                    full_assistant_message.append(agent_output_content)
                            else:
                                logger.debug(
                                    f"Stream: No Command output or no messages in update for {agent_name}"
                                )
                                if isinstance(output, Command):
                                    logger.debug(
                                        f"Stream: Command goto: {output.goto}, update keys: {list(output.update.keys()) if output.update else 'None'}"
                                    )
                                else:
                                    logger.debug("Stream: Output is not a Command object")

                            # Check for plan/todos in orchestrator node output (after processing messages)
                            if node_name == "orchestrator":
                                import json

                                # Get Command output and snapshot
                                cmd_output = event.get("data", {}).get("output", None)
                                snapshot = event.get("data", {}).get("snapshot", {})

                                # ALWAYS check snapshot first (contains accumulated state with ALL todos including completed)
                                # Command.update only has NEW todos from this invocation
                                # Snapshot has ALL todos merged via operator.add reducer
                                plan_data = None

                                # Check snapshot first (has merged state with all todos)
                                if isinstance(snapshot, dict):
                                    # Debug: Log snapshot structure
                                    logger.debug(f"Snapshot keys: {list(snapshot.keys())}")

                                    # Prefer plan object if it exists (has proper structure with status)
                                    if "plan" in snapshot:
                                        plan_obj = snapshot["plan"]
                                        logger.debug(
                                            f"Found plan in snapshot, type: {type(plan_obj)}"
                                        )
                                        # Convert Plan object to dict if needed
                                        if hasattr(plan_obj, "model_dump"):
                                            plan_data = plan_obj.model_dump()
                                        elif hasattr(plan_obj, "dict"):
                                            plan_data = plan_obj.dict()
                                        elif isinstance(plan_obj, dict):
                                            plan_data = plan_obj
                                        else:
                                            plan_data = {"title": "Execution Plan", "steps": []}
                                        logger.debug("Using plan object from snapshot")
                                    elif "todos" in snapshot:
                                        todos = snapshot.get("todos", [])
                                        logger.debug(f"Found todos in snapshot: {len(todos)} items")

                                        # Convert todos to plan format
                                        if todos:
                                            # Process todos in FORWARD order to preserve chronological order
                                            # Update status when we see newer versions of same todo
                                            # This preserves the order todos were first created, while showing latest status
                                            seen_contents = {}  # Track first occurrence index to preserve order
                                            valid_todos = []
                                            status_priority = {
                                                "completed": 3,
                                                "in_progress": 2,
                                                "failed": 1,
                                                "pending": 0,
                                            }

                                            for todo in todos:
                                                if not todo:
                                                    continue

                                                # Extract content for deduplication
                                                if isinstance(todo, dict):
                                                    content = todo.get("content", str(todo))
                                                    status = todo.get("status", "pending")
                                                else:
                                                    content = str(todo)
                                                    status = "pending"

                                                current_priority = status_priority.get(status, 0)

                                                if content not in seen_contents:
                                                    # First time seeing this todo - add it (preserves chronological order)
                                                    seen_contents[content] = len(valid_todos)
                                                    valid_todos.append(
                                                        {
                                                            "content": content,
                                                            "status": status,
                                                            "original": todo,
                                                        }
                                                    )
                                                else:
                                                    # We've seen this todo before - update status if newer has better/equal priority
                                                    existing_idx = seen_contents[content]
                                                    existing_status = valid_todos[existing_idx][
                                                        "status"
                                                    ]
                                                    existing_priority = status_priority.get(
                                                        existing_status, 0
                                                    )

                                                    # Update status in place (preserves order, updates status)
                                                    if current_priority >= existing_priority:
                                                        valid_todos[existing_idx]["status"] = status
                                                        valid_todos[existing_idx]["original"] = todo

                                            # Log todo statuses for debugging
                                            if valid_todos:
                                                statuses = [t["status"] for t in valid_todos]
                                                logger.debug(
                                                    f"Todo statuses after deduplication: {statuses}"
                                                )

                                            if valid_todos:
                                                plan_data = {
                                                    "title": "Execution Plan",
                                                    "thought": "Task breakdown",
                                                    "steps": [
                                                        {
                                                            "title": todo["content"][:100],
                                                            "status": todo["status"],
                                                            "agent_name": "Orchestrator",
                                                            "description": todo["content"],
                                                        }
                                                        for todo in valid_todos
                                                    ],
                                                }
                                                logger.debug(
                                                    f"Converted {len(valid_todos)} todos to plan format from snapshot"
                                                )

                                # Merge snapshot todos with Command.update todos if both exist
                                # This ensures we have all todos with latest status updates
                                if (
                                    isinstance(snapshot, dict)
                                    and "todos" in snapshot
                                    and isinstance(cmd_output, Command)
                                    and cmd_output.update
                                    and "todos" in cmd_output.update
                                ):
                                    snapshot_todos = snapshot.get("todos", [])
                                    update_todos = cmd_output.update.get("todos", [])

                                    # Combine todos: snapshot has accumulated, update has latest
                                    # Process in forward order to preserve chronological order
                                    all_todos = snapshot_todos + update_todos

                                    seen_contents = {}  # Track first occurrence index to preserve order
                                    valid_todos = []
                                    status_priority = {
                                        "completed": 3,
                                        "in_progress": 2,
                                        "failed": 1,
                                        "pending": 0,
                                    }

                                    for todo in all_todos:
                                        if not todo:
                                            continue

                                        if isinstance(todo, dict):
                                            content = todo.get("content", str(todo))
                                            status = todo.get("status", "pending")
                                        else:
                                            content = str(todo)
                                            status = "pending"

                                        current_priority = status_priority.get(status, 0)

                                        if content not in seen_contents:
                                            # First time seeing this todo - add it (preserves chronological order)
                                            seen_contents[content] = len(valid_todos)
                                            valid_todos.append(
                                                {"content": content, "status": status}
                                            )
                                        else:
                                            # Update status in place if newer has better/equal priority
                                            existing_idx = seen_contents[content]
                                            existing_status = valid_todos[existing_idx]["status"]
                                            existing_priority = status_priority.get(
                                                existing_status, 0
                                            )

                                            if current_priority >= existing_priority:
                                                valid_todos[existing_idx]["status"] = status

                                    if seen_contents and not plan_data:
                                        plan_data = {
                                            "title": "Execution Plan",
                                            "thought": "Task breakdown",
                                            "steps": [
                                                {
                                                    "title": todo["content"][:100],
                                                    "status": todo["status"],
                                                    "agent_name": "Orchestrator",
                                                    "description": todo["content"],
                                                }
                                                for todo in valid_todos
                                            ],
                                        }
                                        logger.debug(
                                            f"Merged {len(snapshot_todos)} snapshot + {len(update_todos)} update todos into {len(valid_todos)} deduplicated todos"
                                        )

                                # Fallback to Command.update only if snapshot doesn't have todos/plan
                                if (
                                    not plan_data
                                    and isinstance(cmd_output, Command)
                                    and cmd_output.update
                                ):
                                    update = cmd_output.update
                                    if "plan" in update:
                                        plan_data = update["plan"]
                                        logger.debug("Found plan in Command.update (fallback)")
                                    elif "todos" in update:
                                        todos = update.get("todos", [])
                                        logger.debug(
                                            f"Found todos in Command.update (fallback): {len(todos)} items"
                                        )
                                        # Convert todos to plan format
                                        if todos:
                                            valid_todos = [t for t in todos if t]
                                            if valid_todos:
                                                plan_data = {
                                                    "title": "Execution Plan",
                                                    "thought": "Task breakdown",
                                                    "steps": [
                                                        {
                                                            "title": todo.get("content", str(todo))[
                                                                :100
                                                            ]
                                                            if isinstance(todo, dict)
                                                            else str(todo)[:100],
                                                            "status": todo.get("status", "pending")
                                                            if isinstance(todo, dict)
                                                            else "pending",
                                                            "agent_name": "Orchestrator",
                                                            "description": todo.get(
                                                                "content", str(todo)
                                                            )
                                                            if isinstance(todo, dict)
                                                            else str(todo),
                                                        }
                                                        for todo in valid_todos
                                                    ],
                                                }
                                                logger.debug(
                                                    f"Converted {len(valid_todos)} todos to plan format from Command.update (fallback)"
                                                )

                                if plan_data:
                                    # Convert Plan object to dict if needed
                                    if hasattr(plan_data, "model_dump"):
                                        plan_dict = plan_data.model_dump()
                                    elif hasattr(plan_data, "dict"):
                                        plan_dict = plan_data.dict()
                                    elif isinstance(plan_data, dict):
                                        plan_dict = plan_data
                                    else:
                                        # Fallback: convert to string
                                        plan_dict = {
                                            "error": "Could not serialize plan",
                                            "raw": str(plan_data),
                                        }

                                    plan_json = json.dumps(plan_dict)
                                    plan_event = StreamEvent(
                                        type="plan",
                                        content=plan_json,
                                        thread_id=conversation_id,
                                    )
                                    yield f"data: {plan_event.model_dump_json()}\n\n"
                                    logger.info(
                                        f"Emitted plan event from orchestrator for conversation: {conversation_id}"
                                    )

                        # Filter for chat model stream events (streaming LLMs)
                        # DISABLED: This handler emitted ALL LLM tokens (from Coder, SQL Agent,
                        # and Orchestrator) as "token" events, causing worker code/SQL
                        # to leak into the main response area. The on_chain_end handler already
                        # correctly emits: worker responses as agent_end (collapsed sections),
                        # orchestrator final response as chunked tokens, and skips routing messages.
                        if event_name == "on_chat_model_stream":
                            pass  # Intentionally disabled — see on_chain_end handler above

                        # Capture tool results from on_tool_end events
                        elif event_name == "on_tool_end":
                            tool_name = event["data"].get("name", "")
                            tool_output = event["data"].get("output", "")

                            # Capture tool results that contain images
                            if tool_output:
                                # Handle case where output might be a ToolMessage object
                                if hasattr(tool_output, "content"):
                                    tool_output = tool_output.content

                                if isinstance(tool_output, str):
                                    # Extract markdown images from tool output
                                    # Pattern: ![filename](data:image/...;base64,...)
                                    image_pattern = r"!\[[^\]]*\]\(data:image/[^)]+\)"
                                    images = re.findall(image_pattern, tool_output)
                                    if images:
                                        tool_images.extend(images)
                                        logger.info(f"Found {len(images)} image(s) in tool output")

                                    # Extract S3 file references for file events
                                    # Pattern: S3_FILE[{"bucket": "...", "key": "..."}]
                                    s3_pattern = r"S3_FILE\[(\{[^\}]+\})\]"
                                    s3_matches = re.findall(s3_pattern, tool_output)
                                    if s3_matches:
                                        import json
                                        import os
                                        from src.service.s3 import generate_presigned_url

                                        for match in s3_matches:
                                            try:
                                                s3_file = json.loads(match)
                                                bucket = s3_file.get("bucket", "")
                                                key = s3_file.get("key", "")

                                                if bucket and key:
                                                    # Determine file type from extension
                                                    file_extension = os.path.splitext(key)[
                                                        1
                                                    ].lower()
                                                    is_image = file_extension in [
                                                        ".png",
                                                        ".jpg",
                                                        ".jpeg",
                                                        ".gif",
                                                        ".svg",
                                                    ]

                                                    # Determine content type
                                                    content_type_map = {
                                                        ".png": "image/png",
                                                        ".jpg": "image/jpeg",
                                                        ".jpeg": "image/jpeg",
                                                        ".gif": "image/gif",
                                                        ".svg": "image/svg+xml",
                                                        ".csv": "text/csv",
                                                        ".json": "application/json",
                                                        ".txt": "text/plain",
                                                    }
                                                    content_type = content_type_map.get(
                                                        file_extension, "application/octet-stream"
                                                    )

                                                    # Generate presigned URL (expires in 1 hour)
                                                    presigned_url = generate_presigned_url(
                                                        bucket, key, expiration=3600
                                                    )

                                                    # Emit file event
                                                    file_event = StreamEvent(
                                                        type="file",
                                                        content=f"Generated: {os.path.basename(key)}",
                                                        thread_id=conversation_id,
                                                        agent_name=metadata.get("agent_name"),
                                                        file_metadata={
                                                            "filename": os.path.basename(key),
                                                            "s3_bucket": bucket,
                                                            "s3_key": key,
                                                            "file_type": "visualization"
                                                            if is_image
                                                            else "data",
                                                            "content_type": content_type,
                                                            "url": presigned_url,
                                                            "is_image": is_image,
                                                        },
                                                    )
                                                    yield f"data: {file_event.model_dump_json()}\n\n"
                                                    logger.info(
                                                        f"Emitted file event for s3://{bucket}/{key}"
                                                    )
                                            except Exception as e:
                                                logger.warning(
                                                    f"Failed to parse S3 file metadata: {e}"
                                                )

                    # Append any images found in tool results after LLM response
                    if tool_images:
                        logger.info(f"Appending {len(tool_images)} image(s) to stream")
                        # Send images as separate tokens to ensure they're displayed
                        for idx, image_markdown in enumerate(tool_images):
                            # Add newline before first image for proper markdown formatting
                            content = f"\n{image_markdown}" if idx == 0 else image_markdown
                            image_event = StreamEvent(
                                type="token",
                                content=content,
                                thread_id=conversation_id,
                            )
                            yield f"data: {image_event.model_dump_json()}\n\n"

                    logger.info(f"Stream completed for conversation: {conversation_id}")

                    # Auto-generate title for first message in conversation
                    # Get final state to extract assistant's response (works for both streaming and structured output)
                    if is_new_conversation:
                        try:
                            # Get the final state from checkpointer to extract assistant's response
                            # This works even when structured output is used (which doesn't stream tokens)
                            final_state = await agent.aget_state(config)
                            assistant_message = None

                            if final_state and final_state.values.get("messages"):
                                messages = final_state.values["messages"]
                                # Find the last assistant/coordinator/orchestrator message
                                for msg in reversed(messages):
                                    if isinstance(msg, (AIMessage, HumanMessage)) and hasattr(
                                        msg, "name"
                                    ):
                                        if msg.name in ["coordinator", "orchestrator"]:
                                            assistant_message = msg.content
                                            break
                                    elif isinstance(msg, AIMessage):
                                        assistant_message = msg.content
                                        break

                            # Fallback to streaming tokens if we collected them
                            if not assistant_message and full_assistant_message:
                                assistant_message = "".join(full_assistant_message)

                            if assistant_message:
                                logger.info(
                                    f"🎯 Triggering title generation for new conversation {conversation_id}"
                                )
                                # Fire and forget - don't await to avoid blocking the end event
                                # Use asyncio.ensure_future to schedule it on the event loop
                                asyncio.ensure_future(
                                    conversation_service.auto_generate_and_update_title(
                                        conversation_id=conversation_id,
                                        user_id=user_id or "anonymous",
                                        user_message=request.message,
                                        assistant_message=assistant_message,
                                    )
                                )
                            else:
                                logger.warning(
                                    f"⚠️  No assistant message found for title generation in conversation {conversation_id}"
                                )
                        except Exception as e:
                            logger.warning(
                                f"Failed to trigger title generation: {e}", exc_info=True
                            )

                    # Phase 0.5: fire-and-forget memory extraction (pilot-gated, default off).
                    # Re-uses the final-state assistant_message captured above when it's a new
                    # conversation; for continuing conversations we fetch it the same way.
                    try:
                        if (
                            settings.memory_extraction_enabled
                            and user_id
                            and user_id in _pilot_user_ids_set()
                        ):
                            extraction_assistant_message: str | None = None
                            if is_new_conversation:
                                extraction_assistant_message = (
                                    assistant_message if "assistant_message" in locals() else None
                                )
                            else:
                                try:
                                    _final_state = await agent.aget_state(config)
                                    if _final_state and _final_state.values.get("messages"):
                                        for _msg in reversed(_final_state.values["messages"]):
                                            if isinstance(_msg, AIMessage):
                                                extraction_assistant_message = _msg.content
                                                break
                                            if (
                                                isinstance(_msg, HumanMessage)
                                                and getattr(_msg, "name", None) == "coordinator"
                                            ):
                                                extraction_assistant_message = _msg.content
                                                break
                                except Exception:
                                    logger.debug(
                                        "memory_extraction: failed to read final state",
                                        exc_info=True,
                                    )

                            if extraction_assistant_message:
                                from src.service.memory import extract_memories_for_turn

                                asyncio.ensure_future(
                                    extract_memories_for_turn(
                                        thread_id=conversation_id,
                                        user_id=user_id,
                                        project_id=getattr(request, "project_id", None),
                                        database_id=getattr(request, "database_id", None),
                                        user_message=request.message,
                                        assistant_message=extraction_assistant_message,
                                    )
                                )
                    except Exception as _e:
                        logger.warning(f"Failed to schedule memory extraction: {_e}")

                    # Estimate token usage from final state
                    token_usage = None
                    try:
                        end_state = await agent.aget_state(config)
                        if end_state and end_state.values.get("messages"):
                            state_messages = end_state.values["messages"]
                            estimated_tokens = count_tokens_approximately(state_messages)
                            max_tokens = int(
                                settings.context_model_max_tokens
                                * settings.context_summary_trigger_fraction
                            )
                            token_usage = {
                                "estimated_tokens": estimated_tokens,
                                "max_tokens": max_tokens,
                                "usage_pct": round((estimated_tokens / max_tokens) * 100, 1)
                                if max_tokens > 0
                                else 0,
                            }
                    except Exception as e:
                        logger.warning(f"Failed to estimate token usage: {e}")

                    # Phase 2 Workstream C — finalize the root agent.request
                    # span with the post-stream enrichment: content-derived
                    # trace name, turn label (t0/t1/t2 …), turn tags, and
                    # the synthesized output. All no-ops when OTel is off;
                    # output + payload attrs additionally honor
                    # trace_capture_payloads.
                    try:
                        # Synthesized assistant output — the same text the
                        # title-gen + memory-extraction code already reads.
                        output_text: str | None = None
                        if "assistant_message" in locals() and assistant_message:
                            output_text = assistant_message
                        elif full_assistant_message:
                            output_text = "".join(full_assistant_message)

                        # Turn index: count USER HumanMessages in the final
                        # state and subtract 1 so the current turn is
                        # zero-indexed. Internal routing messages (coordinator
                        # responses, worker echoes) also use HumanMessage
                        # under the hood but always have a .name attribute
                        # set — the USER turn is the unnamed one. Filter on
                        # that to avoid overcounting t0 → t2 → t4 …
                        turn_index: int | None = None
                        try:
                            if (
                                "end_state" in locals()
                                and end_state
                                and end_state.values.get("messages")
                            ):
                                user_turns = sum(
                                    1
                                    for m in end_state.values["messages"]
                                    if isinstance(m, HumanMessage) and not getattr(m, "name", None)
                                )
                                turn_index = max(user_turns - 1, 0)
                        except Exception:  # noqa: BLE001
                            # Turn index is a nice-to-have, not load-bearing.
                            turn_index = None

                        # Preserve the tag list we set at stream-open so the
                        # finalize step can APPEND turn tags rather than
                        # REPLACE (OTel set_attribute overwrites lists).
                        existing_tags: list[str] | None = None
                        try:
                            open_attrs = getattr(_request_span, "attributes", None)
                            if open_attrs is not None:
                                raw = open_attrs.get("langfuse.tags")
                                if raw is not None:
                                    existing_tags = list(raw)
                        except Exception:  # noqa: BLE001
                            existing_tags = None

                        finalize_attrs = build_request_trace_finalize_attrs(
                            first_user_message=request.message,
                            output=output_text or "",
                            turn_index=turn_index,
                            existing_tags=existing_tags,
                            research_mode=request.research_mode,
                        )
                        if finalize_attrs:
                            _request_span.set_attributes(finalize_attrs)
                    except Exception as _e:  # noqa: BLE001
                        logger.debug("failed to finalize trace attrs: %s", _e)

                    # Send end event
                    end_event = StreamEvent(
                        type="end",
                        content="",
                        thread_id=conversation_id,
                        token_usage=token_usage,
                    )
                    yield f"data: {end_event.model_dump_json()}\n\n"

            except Exception as e:
                # CRITICAL: Error handling INSIDE generator
                logger.error(f"Error in stream: {e}", exc_info=True)
                error_event = StreamEvent(
                    type="error",
                    content=str(e),
                    thread_id=conversation_id if "conversation_id" in locals() else None,
                )
                yield f"data: {error_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
