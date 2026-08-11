"""Orchestrator planning tool for managing execution plans.

This tool provides a clean interface for the orchestrator to create and update
the execution plan, which serves as both internal state tracking and frontend observability.
"""

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from langchain.tools import InjectedToolCallId
from src.models.plan import Plan, PlanStep
from src.service.observability import trace_tool


MANAGE_PLAN_TOOL_DESCRIPTION = """Use this tool to create, update, and manage a structured execution plan for your current work session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.ser.

This tool REPLACES the entire plan each time you call it. You can:
- **Create new steps**: Include them in the steps list you pass
- **Update existing steps**: Change the status field (pending → in_progress → completed)
- **Remove steps**: Simply exclude them from the list you pass (they will be deleted)

Only use this tool if you think it will be helpful in staying organized. If the user's request is trivial and takes less than 3 steps, it is better to NOT use this tool and just do the task directly.

## When to Use This Tool
Use this tool in these scenarios:

1. Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
5. The plan may need future revisions or updates based on results from the first few steps

## How to Use This Tool
1. When you start working on a task - Mark it as in_progress BEFORE beginning work.
2. After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation.
3. You can also update future tasks, such as deleting them if they are no longer necessary, or adding new tasks that are necessary. Don't change previously completed tasks.
4. You can make several updates to the todo list at once. For example, when you complete a task, you can mark the next task you need to start as in_progress.
5. To remove a todo - simply don't include it in the todos list you pass to this tool.

## When NOT to Use This Tool
It is important to skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (you can have multiple tasks in_progress at a time if they are not related to each other and can be run in parallel)
   - completed: Task finished successfully

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Complete current tasks before starting new ones
   - Remove tasks that are no longer relevant by excluding them from the list
   - IMPORTANT: When you write this todo list, you should mark your first task (or tasks) as in_progress immediately!
   - IMPORTANT: Unless all tasks are completed, you should always have at least one task in_progress to show the user that you are working on something.

3. **Task Completion Requirements**:
   - ONLY mark a task as completed when you have FULLY accomplished it
   - If you encounter errors, blockers, or cannot finish, keep the task as in_progress
   - When blocked, create a new task describing what needs to be resolved
   - Never mark a task as completed if:
     - There are unresolved issues or errors
     - Work is partial or incomplete
     - You encountered blockers that prevent completion
     - You couldn't find necessary resources or dependencies
     - Quality standards haven't been met

4. **Task Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names

Being proactive with task management demonstrates attentiveness and ensures you complete all requirements successfully
Remember: If you only need to make a few tool calls to complete a task, and it is clear what you need to do, it is better to just do the task directly and NOT call this tool at all."""


@trace_tool
@tool(description=MANAGE_PLAN_TOOL_DESCRIPTION)
def manage_plan(
    steps: list[dict],
    thought: str = "Breaking down the task into actionable steps",
    title: str = "Execution Plan",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Create, update, and manage the execution plan for your current work session.

    Args:
        steps: List of plan steps with agent_name, description, and status
        thought: Your reasoning about the task breakdown
        title: Title for the execution plan

    Each step should have:
    - agent_name: 'coder', 'sql_agent', or 'orchestrator'
    - description: Detailed description of what needs to be done
    - status: 'pending', 'in_progress', or 'completed'

    Example step:
    {
        "agent_name": "sql_agent",
        "description": "Query ClinVar for pathogenic BRCA1 variants",
        "status": "in_progress"
    }
    """
    # Convert dict steps to PlanStep objects
    # Extract agent_name from description if not provided separately
    plan_steps = []
    for step in steps:
        description = step.get("description", "")
        agent_name = step.get("agent_name", "orchestrator")

        # If agent_name is default and description starts with "agent: ", extract it
        if agent_name == "orchestrator" and description and ":" in description:
            parts = description.split(":", 1)
            potential_agent = parts[0].strip().lower()
            if potential_agent in ["coder", "sql_agent"]:
                agent_name = potential_agent
                description = parts[1].strip()  # Remove agent prefix from description

        plan_steps.append(
            PlanStep(
                agent_name=agent_name,
                title=description[:100],  # Use description as title (without agent prefix)
                description=description,
                status=step.get("status", "pending"),
            )
        )

    # Create Plan object
    plan = (
        Plan(
            thought=thought,
            title=title,
            steps=plan_steps,
        )
        if plan_steps
        else None
    )

    return Command(
        update={
            "plan": plan,
            "messages": [
                ToolMessage(
                    f"Updated execution plan with {len(plan_steps)} step(s)",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
