"""LangGraph node implementations for coordinator, orchestrator, and workers."""

import logging
from typing import Literal, Union

from langchain.agents.middleware.summarization import count_tokens_approximately
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, trim_messages
from langgraph.types import Command

from src.config.settings import settings
from src.graph.state import AgentState
from src.graph.types import CoordinatorResponse
from src.agents.coder import create_coder_agent
from src.agents.sql import get_sql_agent
from src.agents.researcher import create_researcher_agent
from src.agents.orchestrator import get_orchestrator_agent
from src.service.llm import LLMService
from src.service.observability import trace_node
from src.prompts.template import get_processed_prompt_with_database_context
from src.utils.context import thread_id_context


def _strip_tool_messages(messages: list) -> list:
    """Remove ToolMessages and tool call metadata for downstream LLM calls."""
    cleaned_messages = []
    for message in messages:
        if getattr(message, "type", None) == "tool":
            continue
        if isinstance(message, AIMessage) and message.tool_calls:
            cleaned_kwargs = dict(message.additional_kwargs)
            cleaned_kwargs.pop("tool_calls", None)
            cleaned_kwargs.pop("function_call", None)
            cleaned_messages.append(
                AIMessage(
                    content=message.content,
                    additional_kwargs=cleaned_kwargs,
                    response_metadata=message.response_metadata,
                    name=message.name,
                )
            )
        else:
            cleaned_messages.append(message)
    return cleaned_messages


def _prepare_worker_messages(state: AgentState) -> dict:
    """Remap message roles so worker LLMs see correct role assignments.

    Workers created via langchain.agents.create_agent receive the full message
    history. The LangChain ChatOpenAI wrapper maps:
      AIMessage  → role: assistant
      HumanMessage → role: user

    Problem: Orchestrator output is AIMessage(name="orchestrator"), which the
    worker LLM interprets as its OWN past response. The worker then concludes
    "I already handled this" and returns empty.

    Fix: Remap orchestrator AIMessages to HumanMessages so the worker sees them
    as instructions FROM someone else (role: user), not its own output.

    This returns a shallow copy of state — the original graph state is untouched,
    so streaming, checkpointing, and all consumers keep working.
    """
    remapped = []
    for msg in state["messages"]:
        if isinstance(msg, AIMessage) and getattr(msg, "name", None) == "orchestrator":
            remapped.append(
                HumanMessage(
                    content=f"[Orchestrator Task]\n{msg.content}",
                    name="orchestrator_task",
                )
            )
        else:
            remapped.append(msg)
    return {**state, "messages": remapped}


logger = logging.getLogger(__name__)


@trace_node("coordinator")
def coordinator_node(state: AgentState) -> Command[Literal["orchestrator", "__end__"]]:
    """Coordinator node that communicates with customers.

    Uses structured output for type-safe routing decisions.
    """
    logger.info("Coordinator talking.")

    # Get coordinator prompt with database context and apply to messages
    system_prompt = get_processed_prompt_with_database_context("coordinator")

    # Trim messages to stay within context window (coordinator uses raw LLM, not create_agent)
    max_coordinator_tokens = int(
        settings.context_model_max_tokens * settings.context_summary_trigger_fraction
    )
    trimmed = trim_messages(
        state["messages"],
        max_tokens=max_coordinator_tokens,
        strategy="last",
        token_counter=count_tokens_approximately,
        include_system=True,
        start_on="human",
    )
    messages = trimmed + [HumanMessage(content=system_prompt)]

    # Use structured output for type-safe coordinator decisions
    # Structured outputs require streaming=False (streaming chunks can't be parsed as JSON)
    # Use provider-aware method selection (function_calling for Bedrock/Anthropic,
    # json_schema for OpenAI/GCP) — see LLMService.get_structured_output_method
    coordinator_decision = (
        LLMService.get_llm_by_agent("coordinator", streaming=False)
        .with_structured_output(
            CoordinatorResponse,
            method=LLMService.get_structured_output_method_for_agent("coordinator"),
        )
        .invoke(messages)
    )

    logger.debug(f"Current state messages: {state['messages']}")
    logger.debug(f"Coordinator decision: {coordinator_decision}")

    # Log reasoning if provided
    if coordinator_decision.reasoning:
        logger.info(f"Coordinator reasoning: {coordinator_decision.reasoning}")

    if coordinator_decision.action == "handoff_to_orchestrator":
        # When handing off to orchestrator, include coordinator's reasoning for visibility
        # (orchestrator will handle the final response, but coordinator's reasoning is useful for observability)
        # State is preserved automatically - orchestrator will receive original user message
        logger.info("Coordinator routing to orchestrator")
        logger.debug(
            f"Preserving original user message: {state['messages'][-1].content if state['messages'] else 'No messages'}"
        )

        # Store reasoning and response separately (reasoning as SystemMessage, response as AIMessage)
        # When routing: include reasoning (as "inner thought"), skip response (orchestrator provides it)
        # When responding: include both reasoning and response
        messages_to_add = []

        if coordinator_decision.reasoning:
            # Store reasoning as SystemMessage with special name for streaming endpoint to identify
            reasoning_message = SystemMessage(
                content=coordinator_decision.reasoning, name="coordinator_reasoning"
            )
            messages_to_add.append(reasoning_message)

        # When routing, don't include response (orchestrator handles the answer)
        # Response would be included when action="respond"

        if messages_to_add:
            return Command(goto="orchestrator", update={"messages": messages_to_add})
        return Command(goto="orchestrator")
    else:
        # When responding directly, include both reasoning (if available) and response
        # This ensures simple queries get saved to checkpoint with full context
        if not coordinator_decision.response:
            logger.warning("Coordinator action is 'respond' but no response content provided")
            coordinator_decision.response = "I'm here to help! How can I assist you today?"

        messages_to_add = []

        # Add reasoning if available (as SystemMessage for inner thought)
        if coordinator_decision.reasoning:
            reasoning_message = SystemMessage(
                content=coordinator_decision.reasoning, name="coordinator_reasoning"
            )
            messages_to_add.append(reasoning_message)

        # Add response as an AIMessage — this is the assistant's answer to the
        # user, so it MUST map to role: assistant.
        #
        # It used to be a HumanMessage(name="coordinator"), which LangChain maps
        # to role: user. On the next turn the coordinator then saw a history made
        # up entirely of user turns — its own past answers included — and could no
        # longer tell the user's new question apart from its own previous reply.
        # In practice it re-answered the PREVIOUS question and offered the actual
        # new one back as a "suggestion". See test_coordinator_response_role.py.
        #
        # Note this is unrelated to the AIMessage → HumanMessage remap in
        # _prepare_worker_messages: that one is a throwaway copy handed to a
        # worker LLM, and deliberately never reaches graph state.
        response_message = AIMessage(content=coordinator_decision.response, name="coordinator")
        messages_to_add.append(response_message)

        logger.info("Coordinator responding directly")
        return Command(goto="__end__", update={"messages": messages_to_add})


@trace_node("orchestrator")
async def orchestrator_node(
    state: AgentState,
) -> Command[
    Union[
        Literal["coder"],
        Literal["sql_agent"],
        Literal["researcher"],
        Literal["__end__"],
    ]
]:
    """Orchestrator node with custom plan tool and structured routing.

    This replaces the legacy planner+supervisor combination.
    Uses custom manage_plan tool for planning and automatic structured output strategy (ProviderStrategy/ToolStrategy) for routing decisions
    and final synthesis in a single LLM call.
    """
    logger.info("Orchestrator processing request")

    # Get current plan and steps
    current_plan = state.get("plan")
    current_steps = current_plan.steps if current_plan else []

    if current_steps:
        logger.info(f"Orchestrator: Current plan has {len(current_steps)} step(s):")
        for i, step in enumerate(current_steps, 1):
            logger.info(
                f"  [{i}] {step.agent_name}: {step.description[:80]} (status: {step.status})"
            )

        # Count status breakdown
        pending_count = sum(1 for step in current_steps if step.status == "pending")
        in_progress_count = sum(1 for step in current_steps if step.status == "in_progress")
        completed_count = sum(1 for step in current_steps if step.status == "completed")
        logger.info(
            f"Orchestrator: Step status breakdown - Pending: {pending_count}, In Progress: {in_progress_count}, Completed: {completed_count}"
        )

    # Check if a worker agent just completed by examining message history
    message_name = None
    if state["messages"]:
        last_message = state["messages"][-1]
        message_name = getattr(last_message, "name", None)
        if message_name in ["researcher", "coder", "sql_agent"]:
            logger.info(
                f"🔍 Orchestrator: Detected worker completion - Agent '{message_name}' just finished"
            )
            logger.info(
                f"📋 Orchestrator: Looking for steps assigned to '{message_name}' that should be marked completed"
            )

            # Find which steps should be marked as completed
            matching_steps = [
                step
                for step in current_steps
                if step.agent_name == message_name and step.status in ["pending", "in_progress"]
            ]
            if matching_steps:
                logger.info(
                    f"📌 Found {len(matching_steps)} step(s) that should be marked completed:"
                )
                for step in matching_steps:
                    logger.info(
                        f"   - {step.agent_name}: {step.description[:100]} (current status: {step.status})"
                    )
            else:
                logger.warning(f"⚠️  No matching steps found for worker '{message_name}'")

        original_user_message = state["messages"][-1].content
        logger.debug(f"Orchestrator received original user message: {original_user_message[:200]}")

    # Get research_mode from state (defaults to "standard" if not set)
    research_mode = state.get("research_mode", "standard")
    logger.debug(f"Orchestrator using research_mode: {research_mode}")

    # Re-invoked per LangGraph loop; returns a structured routing decision
    # handled by the rest of this function.
    orchestrator_agent = get_orchestrator_agent(research_mode=research_mode)

    # Log message history being passed to orchestrator (last 5 messages)
    logger.info("📨 Messages being passed to orchestrator (last 5):")
    for i, msg in enumerate(state["messages"][-5:]):
        msg_type = type(msg).__name__
        msg_name = getattr(msg, "name", "")
        msg_content_preview = msg.content[:100] if hasattr(msg, "content") else str(msg)[:100]
        logger.info(f"   [{i}] {msg_type} (name='{msg_name}'): {msg_content_preview}...")

    # Invoke orchestrator agent asynchronously
    # - manage_plan tool handles planning (custom implementation)
    # - response_format=OrchestratorResponse automatically uses ProviderStrategy for OpenAI/Gemini or ToolStrategy fallback
    # - Both happen in a single LLM call
    logger.info("🤖 Invoking orchestrator agent...")
    result = await orchestrator_agent.ainvoke(
        state,
        config={"metadata": {"agent_name": "Orchestrator"}},
    )
    logger.info("✅ Orchestrator agent invocation complete")

    # Log ALL messages in result to see tool calls
    result_messages = result.get("messages", [])
    logger.info(f"📬 Result messages from orchestrator ({len(result_messages)} total):")
    for i, msg in enumerate(result_messages):
        msg_type = type(msg).__name__
        msg_name = getattr(msg, "name", "")

        # Check for tool calls
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            logger.info(
                f"   [{i}] {msg_type} (name='{msg_name}') with {len(msg.tool_calls)} tool call(s):"
            )
            for tc in msg.tool_calls:
                tool_name = tc.get("name", "unknown")
                tool_args = tc.get("args", {})
                if tool_name == "manage_plan":
                    logger.info(
                        f"      🛠️  manage_plan called with {len(tool_args.get('steps', []))} step(s):"
                    )
                    for step in tool_args.get("steps", []):
                        logger.info(
                            f"         - {step.get('agent_name', '')}: {step.get('description', '')[:80]} (status: {step.get('status')})"
                        )
                else:
                    logger.info(f"      🛠️  {tool_name} called")
        else:
            msg_content_preview = msg.content[:100] if hasattr(msg, "content") else str(msg)[:100]
            logger.info(f"   [{i}] {msg_type} (name='{msg_name}'): {msg_content_preview}...")

    # Extract plan by looking for ToolMessage from manage_plan in result messages
    # The manage_plan tool returns Command(update={"plan": plan}), but during this node execution,
    # we need to manually extract the plan from the tool call arguments to include it in our Command.update
    # Otherwise, the plan won't be available in the on_chain_end event
    plan = state.get("plan")  # Start with existing plan from state

    # Look for manage_plan tool call in messages to reconstruct the plan
    from src.models.plan import Plan, PlanStep

    for msg in result_messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("name") == "manage_plan":
                    # Found manage_plan call - reconstruct the Plan object
                    tool_args = tc.get("args", {})
                    steps_data = tool_args.get("steps", [])
                    thought = tool_args.get("thought", "")
                    title = tool_args.get("title", "")

                    if steps_data:
                        # Reconstruct Plan from tool arguments using same logic as manage_plan tool
                        # Handle missing fields with defaults (LLM might not provide agent_name/title separately)
                        # Extract agent_name from description if not provided separately
                        plan_steps = []
                        for step in steps_data:
                            description = step.get("description", "")
                            agent_name = step.get("agent_name", "orchestrator")

                            # If agent_name is default and description starts with "agent: ", extract it
                            if agent_name == "orchestrator" and description and ":" in description:
                                parts = description.split(":", 1)
                                potential_agent = parts[0].strip().lower()
                                if potential_agent in ["coder", "sql_agent"]:
                                    agent_name = potential_agent
                                    description = parts[
                                        1
                                    ].strip()  # Remove agent prefix from description

                            plan_steps.append(
                                PlanStep(
                                    agent_name=agent_name,
                                    title=description[
                                        :100
                                    ],  # Use description as title (without agent prefix)
                                    description=description,
                                    status=step.get("status", "pending"),
                                )
                            )

                        plan = Plan(thought=thought, title=title, steps=plan_steps)
                        logger.info(
                            f"📋 Extracted plan from manage_plan tool call: {len(plan_steps)} steps"
                        )
                    break

    # Log plan for observability (doesn't affect routing logic)
    if plan:
        logger.info(f"Orchestrator plan AFTER processing: {plan.title} ({len(plan.steps)} steps)")
        # Check if steps were properly updated
        pending_after = sum(1 for step in plan.steps if step.status == "pending")
        in_progress_after = sum(1 for step in plan.steps if step.status == "in_progress")
        completed_after = sum(1 for step in plan.steps if step.status == "completed")
        logger.info(
            f"Orchestrator: Step status AFTER processing - Pending: {pending_after}, In Progress: {in_progress_after}, Completed: {completed_after}"
        )

        # Compare with state before
        if current_steps:
            completed_before = sum(1 for step in current_steps if step.status == "completed")
            if completed_after > completed_before:
                logger.info(
                    f"Orchestrator: ✅ Successfully marked {completed_after - completed_before} step(s) as completed"
                )
            elif message_name in ["researcher", "coder", "sql_agent"]:
                logger.warning(
                    f"Orchestrator: ⚠️ Worker '{message_name}' completed but NO steps were marked as completed!"
                )

    if plan and hasattr(plan, "thought"):
        logger.info(f"Plan thought: {plan.thought}")

    # Extract orchestrator response from structured_response (added by agent with response_format)
    # THIS is what controls routing - not todos/plan
    orchestrator_response = result.get("structured_response")

    if not orchestrator_response:
        # Fallback: log error and default to __end__ if structured_response missing
        error_msg = "No structured_response found in orchestrator result. Agent may not have returned structured output."
        logger.error(f"Orchestrator: {error_msg}")
        logger.warning("Orchestrator defaulting to __end__ due to missing routing decision")
        # Include plan in update for observability (doesn't affect routing)
        update = {"messages": result["messages"]}
        if plan:
            update["plan"] = plan
        return Command(goto="__end__", update=update)

    # orchestrator_response is already an OrchestratorResponse instance
    goto = orchestrator_response.next

    # Log routing reasoning if provided (for observability)
    if orchestrator_response.reasoning:
        logger.info(f"Routing reasoning: {orchestrator_response.reasoning}")

    # CRITICAL SYSTEM-LEVEL VALIDATION: Check for pending/in_progress steps when routing to __end__
    # If there are remaining steps, OVERRIDE the routing decision and continue the plan
    routing_overridden = False
    response_content = None

    if goto == "__end__" and plan:
        pending_count = sum(1 for step in plan.steps if step.status in ["pending", "in_progress"])
        if pending_count > 0:
            logger.warning(
                f"Orchestrator: ⚠️ LLM tried to route to __end__ with {pending_count} step(s) still pending/in_progress"
            )
            pending_steps = [
                f"{step.agent_name}: {step.description[:100]}"
                for step in plan.steps
                if step.status in ["pending", "in_progress"]
            ]
            logger.warning(f"Orchestrator: Pending steps: {pending_steps}")

            # LOOP PREVENTION: If the worker that just completed has an in_progress step,
            # auto-complete it to prevent infinite loops (LLM forgot to call manage_plan)
            # NOTE: Only auto-complete 'in_progress' steps, NOT 'pending' ones.
            # 'in_progress' = was actively routed to worker, 'pending' = waiting to be executed
            if message_name in ["researcher", "coder", "sql_agent"]:
                # Check if the worker signaled failure (⚠️ TASK FAILED marker)
                last_msg_content = getattr(state["messages"][-1], "content", "")
                worker_failed = "TASK FAILED" in last_msg_content
                if worker_failed:
                    logger.warning(f"Orchestrator: ❌ Worker '{message_name}' signaled TASK FAILED")

                auto_completed_count = 0
                for step in plan.steps:
                    if step.agent_name == message_name and step.status == "in_progress":
                        if worker_failed:
                            logger.info(
                                f"Orchestrator: 🔄 Marking step for '{message_name}' "
                                f"as FAILED (worker returned empty)"
                            )
                            step.status = "failed"
                        else:
                            logger.info(
                                f"Orchestrator: 🔄 Auto-completing step for "
                                f"'{message_name}' (LLM forgot to call manage_plan)"
                            )
                            step.status = "completed"
                        auto_completed_count += 1

                if auto_completed_count > 0:
                    logger.info(
                        f"Orchestrator: ✅ Auto-completed {auto_completed_count} step(s) for '{message_name}'"
                    )
                    # Re-check pending count after auto-completion
                    pending_count = sum(
                        1 for step in plan.steps if step.status in ["pending", "in_progress"]
                    )
                    if pending_count == 0:
                        logger.info(
                            "Orchestrator: ✅ All steps now complete after auto-completion - allowing routing to __end__"
                        )
                        # Don't override - allow routing to __end__
                    else:
                        logger.info(
                            f"Orchestrator: Still have {pending_count} pending step(s) for other agents"
                        )

            # Only override if there are still pending steps after auto-completion
            if pending_count > 0:
                # OVERRIDE: Find the next pending step and route to its agent instead
                # This enforces plan completion - the LLM cannot skip planned steps
                next_step = None
                for step in plan.steps:
                    if step.status in ["pending", "in_progress"]:
                        next_step = step
                        break

                if next_step:
                    # Validate agent_name is a valid worker
                    valid_workers = {"researcher", "coder", "sql_agent"}
                    if next_step.agent_name not in valid_workers:
                        logger.error(
                            f"Orchestrator: Invalid agent_name '{next_step.agent_name}' in plan step - must be one of {valid_workers}"
                        )
                        # Skip this step and try the next one, or allow __end__ if no valid steps remain
                        next_step = None
                        for step in plan.steps:
                            if (
                                step.status in ["pending", "in_progress"]
                                and step.agent_name in valid_workers
                            ):
                                next_step = step
                                break

                    if next_step:
                        # Override routing to continue the plan
                        logger.info(
                            f"Orchestrator: 🔄 OVERRIDING __end__ → routing to {next_step.agent_name} instead"
                        )
                        logger.info(f"Orchestrator: Next step: {next_step.description[:100]}")

                        # Mark this step as in_progress
                        next_step.status = "in_progress"

                        # Override goto to the next step's agent
                        goto = next_step.agent_name
                        routing_overridden = True

                        # Create task instruction for the next step
                        # Include context from previously completed steps if available
                        completed_results = []
                        for step in plan.steps:
                            if (
                                step.status == "completed"
                                and hasattr(step, "result")
                                and step.result
                            ):
                                completed_results.append(
                                    f"- {step.agent_name}: {step.result[:200]}"
                                )

                        context_str = ""
                        if completed_results:
                            context_str = (
                                "\n\nContext from completed steps:\n"
                                + "\n".join(completed_results)
                                + "\n\n"
                            )

                        response_content = f"{context_str}Task: {next_step.description}"
                        logger.info(f"Orchestrator: Generated task instruction for {goto}")

    logger.info(f"Orchestrator routing to: {goto}")

    # Format the orchestrator's response based on routing decision
    # If routing to a worker, show routing decision reasoning (for observability)
    # If routing to __end__, use final_response if provided, otherwise fallback to reasoning
    if goto == "__end__":
        logger.debug("Orchestrator routing to __end__ - preparing final response")
        # Use final_response if provided (should contain synthesized response)
        if orchestrator_response.final_response and orchestrator_response.final_response.strip():
            response_content = orchestrator_response.final_response
            logger.debug(f"Orchestrator: Using final_response (length: {len(response_content)})")
        else:
            # Fallback to reasoning if final_response is missing
            logger.warning(
                "Orchestrator routed to __end__ but no final_response provided, using reasoning as fallback"
            )
            response_content = orchestrator_response.reasoning or "Task completed."
            logger.debug(
                f"Orchestrator: Using reasoning fallback (length: {len(response_content) if response_content else 0})"
            )

        logger.debug(
            f"Orchestrator: Final response_content length: {len(response_content) if response_content else 0}"
        )
        logger.debug(
            f"Orchestrator: Final response_content preview: {response_content[:200] if response_content else 'None'}"
        )
    elif not routing_overridden:
        # Only set response_content from orchestrator_response if not already set by override logic
        # Routing to worker - show routing decision reasoning for observability
        # This helps users understand what the orchestrator is doing
        response_content = orchestrator_response.reasoning or f"Routing to {goto}."
        logger.debug(
            f"Orchestrator: Routing to worker {goto}, response_content preview: {response_content[:100] if response_content else 'None'}"
        )

    # Create a formatted response message for display
    # This is what will be shown to the user
    formatted_message = AIMessage(content=response_content, name="orchestrator")

    logger.debug(
        f"Orchestrator: Created formatted_message with content length: {len(formatted_message.content) if formatted_message.content else 0}"
    )
    logger.info(
        f"Orchestrator: Returning Command with goto={goto}, message content length: {len(formatted_message.content) if formatted_message.content else 0}"
    )

    # Build update dict with messages and plan
    # Include plan for observability - it doesn't affect routing logic
    # Routing is controlled by OrchestratorResponse.next above
    update = {"messages": [formatted_message]}

    # Include plan if it exists (for observability only)
    if plan:
        update["plan"] = plan

    # Return Command with routing decision (from OrchestratorResponse.next)
    # and state updates including plan for observability
    return Command(goto=goto, update=update)


@trace_node("coder")
async def coder_node(state: AgentState) -> Command[Literal["orchestrator"]]:
    """Node for the coder agent that executes Python code."""
    logger.info("Coder agent starting task")

    # Set thread_id in context for tools to access
    thread_id = state.get("thread_id")
    if thread_id:
        thread_id_context.set(thread_id)
        logger.debug(f"Coder node: Set thread_id context to {thread_id}")

    # Extract user_id from thread_id (format: user_id:conversation_id)
    # Keep "anonymous" as a valid user_id for proper S3 path construction
    user_id = None
    if thread_id and ":" in thread_id:
        user_id = thread_id.split(":")[0]  # Keep "anonymous" if present
        logger.debug(f"Coder node: Extracted user_id='{user_id}' from thread_id='{thread_id}'")

    # Load project snippets if project_id is available
    project_snippets = None
    project_id = state.get("project_id")
    logger.info(f"Coder node: project_id={project_id}, user_id={user_id}")
    if project_id and user_id:
        try:
            from src.service.storage.project_service import ProjectService

            project_service = ProjectService()
            snippets = project_service.get_snippets(project_id, user_id)
            project_snippets = [s.model_dump() for s in snippets]
            logger.info(
                f"Coder node: Loaded {len(project_snippets)} snippets for project {project_id}"
            )
            if project_snippets:
                logger.info(f"Coder node: Snippet names: {[s['name'] for s in project_snippets]}")
        except Exception as e:
            logger.warning(f"Coder node: Failed to load project snippets: {e}")
    else:
        logger.info("Coder node: No project_id or user_id - skipping snippet injection")

    # Remap orchestrator AIMessages → HumanMessages so the coder LLM sees them
    # as instructions (role: user) instead of its own past output (role: assistant)
    worker_state = _prepare_worker_messages(state)
    code_language = state.get("code_language", "python")

    coder_agent = create_coder_agent(
        user_id=user_id,
        project_snippets=project_snippets,
        code_language=code_language,
    )
    result = await coder_agent.ainvoke(
        worker_state,
        config={"metadata": {"agent_name": "Coder"}},
    )
    coder_content = result["messages"][-1].content if result.get("messages") else ""

    logger.info("Coder agent completed task")
    logger.debug(f"Coder agent response: {coder_content!r}")

    # Signal failure clearly so the orchestrator knows the coder did NOT succeed
    if not coder_content.strip():
        logger.warning("⚠️  Coder returned empty message - signaling failure to orchestrator")
        coder_content = (
            "⚠️ CODER TASK FAILED: The coder agent did not produce any output. "
            "No code was executed and no results were generated. "
            "The orchestrator should either retry with clearer instructions "
            "or report this step as incomplete."
        )

    return Command(
        update={"messages": [HumanMessage(content=coder_content, name="coder")]},
        goto="orchestrator",
    )


@trace_node("sql_agent")
async def sql_agent_node(state: AgentState) -> Command[Literal["orchestrator"]]:
    """Node for the SQL agent that performs SQL queries and database analysis."""
    logger.info("SQL agent starting task")

    # Set thread_id in context for tools to access
    thread_id = state.get("thread_id")
    if thread_id:
        thread_id_context.set(thread_id)
        logger.debug(f"SQL agent node: Set thread_id context to {thread_id}")

    # Get SQL agent subgraph
    sql_agent_graph = get_sql_agent()

    # Invoke SQL agent subgraph asynchronously
    # Higher recursion limit — a validated query round trip is slow, and the
    # agent needs more iterations for schema exploration + query execution
    result = await sql_agent_graph.ainvoke(
        state,
        config={
            "metadata": {"agent_name": "SQL Agent"},
            "recursion_limit": 50,
        },
    )

    logger.info("SQL agent completed task")

    # Extract the final response message (should be the formatted AIMessage from format_response_node)
    # Filter to get only AIMessage instances to avoid intermediate agent messages
    messages = result.get("messages", [])
    final_message = None

    # Find the last AIMessage (should be from format_response_node)
    for msg in reversed(messages):
        if hasattr(msg, "content") and isinstance(msg, AIMessage):
            final_message = msg
            break

    if not final_message:
        # Fallback: use last message if no AIMessage found
        final_message = messages[-1] if messages else None

    if not final_message:
        final_message = HumanMessage(content="SQL agent completed but no response generated.")

    logger.debug(
        f"SQL agent response: {final_message.content[:200] if final_message else 'No messages'}..."
    )

    sql_content = final_message.content if hasattr(final_message, "content") else str(final_message)

    # Signal failure clearly so the orchestrator knows the SQL agent did NOT succeed
    if not sql_content.strip():
        logger.warning("⚠️  SQL agent returned empty message - signaling failure to orchestrator")
        sql_content = (
            "⚠️ SQL AGENT TASK FAILED: The SQL agent did not produce any output. "
            "No queries were executed and no results were generated. "
            "The orchestrator should either retry with clearer instructions "
            "or report this step as incomplete."
        )

    return Command(
        update={"messages": [HumanMessage(content=sql_content, name="sql_agent")]},
        goto="orchestrator",
    )


@trace_node("researcher")
async def researcher_node(state: AgentState) -> Command[Literal["orchestrator"]]:
    """Node for the researcher agent that searches scientific literature."""
    logger.info("Researcher agent starting task")

    researcher_agent = create_researcher_agent()

    # Remap orchestrator AIMessages → HumanMessages so the researcher LLM reads
    # them as instructions rather than as its own past output.
    worker_state = _prepare_worker_messages(state)

    result = await researcher_agent.ainvoke(
        worker_state,
        config={"metadata": {"agent_name": "Researcher"}},
    )

    logger.info("Researcher agent completed task")

    messages = result.get("messages", [])
    researcher_content = messages[-1].content if messages else ""
    logger.debug(f"Researcher agent response: {str(researcher_content)[:200]}...")

    # Signal failure clearly so the orchestrator knows the researcher did NOT succeed
    if not str(researcher_content).strip():
        logger.warning("⚠️  Researcher returned empty message - signaling failure to orchestrator")
        researcher_content = (
            "⚠️ RESEARCHER TASK FAILED: The researcher agent did not produce any output. "
            "No literature was searched and no results were generated. "
            "The orchestrator should either retry with clearer instructions "
            "or report this step as incomplete."
        )

    return Command(
        update={"messages": [HumanMessage(content=researcher_content, name="researcher")]},
        goto="orchestrator",
    )
