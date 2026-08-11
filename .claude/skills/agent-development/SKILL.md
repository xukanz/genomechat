---
name: agent-development
description: Multi-agent system development patterns, LangGraph workflows, agent architecture, prompt engineering, and agent testing. Use when working with agents, creating workflows, implementing LangGraph nodes, or testing agent behaviors. Triggers on agent, LangGraph, workflow, orchestrator, multi-agent, node.
---

# Agent Development Patterns

## Multi-Agent Architecture

This project implements a hierarchical multi-agent architecture with specialized agents:

### Core Agents

1. **Coordinator** - Initial query handling and task routing
2. **Orchestrator** - Plans multi-step tasks with structured output
3. **Coder** - Python code generation and sandbox execution
4. **SQL Agent** - Database queries (graph-based or agentic mode)

### Agent Files Structure

```
backend/src/
├── agents/
│   ├── coordinator.py        # Query routing
│   ├── orchestrator.py       # Task planning
│   ├── coder.py              # Code generation
│   └── sql_agent.py          # Database queries
├── prompts/
│   ├── coordinator.md        # System prompts
│   ├── orchestrator.md
│   └── coder.md
├── graph/
│   ├── state.py              # LangGraph state definitions
│   └── builder.py            # Workflow construction
└── config/
    └── settings.py           # Agent configuration
```

## Quick Start: LangGraph Workflow

### Basic State Definition

```python
from typing import TypedDict, Annotated, Sequence, Optional
from langgraph.graph import StateGraph
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """State for agent workflow."""
    messages: Annotated[Sequence[BaseMessage], "Chat history"]
    query: str
    plan: Optional[dict]
    results: list[dict]
    error: Optional[str]

workflow = StateGraph(AgentState)
```

### Basic Node Pattern

```python
async def agent_node(state: AgentState) -> AgentState:
    """Execute agent logic."""
    # Validate input first
    if not state["query"]:
        return {**state, "error": "Empty query"}

    try:
        result = await agent.run(state["query"])
        return {**state, "results": result, "error": None}
    except Exception as e:
        return {**state, "error": str(e)}

workflow.add_node("agent", agent_node)
```

### Conditional Routing

```python
def route_next(state: AgentState) -> str:
    """Route to next node based on state."""
    if state.get("error"):
        return "error_handler"
    return "next_step"

workflow.add_conditional_edges("agent", route_next, {...})
```

For detailed patterns, see [langgraph-patterns.md](langgraph-patterns.md).

## Agent Configuration

```python
from pydantic import BaseModel

class AgentConfig(BaseModel):
    """Configuration for an agent."""
    name: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 2000
    system_prompt_path: str
    tools: list[str] = []

AGENT_CONFIGS = {
    "orchestrator": AgentConfig(
        name="Orchestrator",
        model="gpt-4",
        temperature=0.3,
        system_prompt_path="prompts/orchestrator.md",
        tools=["plan", "delegate"]
    ),
    "coder": AgentConfig(
        name="Coder",
        model="gpt-4",
        temperature=0.1,
        system_prompt_path="prompts/coder.md",
        tools=["code_execution", "file_read"]
    )
}
```

## Best Practices

### 1. Agent Specialization

Each agent should have a clear, focused responsibility:

```python
# ✅ Good: Focused agent
class SQLAgent:
    """Specialized agent for database queries."""
    async def execute_query(self, sql: str) -> list[dict]:
        pass

# ❌ Bad: Unfocused agent
class GeneralAgent:
    """Does everything."""
    pass
```

### 2. State Management

Always use typed state (TypedDict) for clarity and type safety.

### 3. Error Handling

Implement robust error handling with retry logic and graceful degradation.

### 4. Observability

Log agent actions with structured logging (structlog) for debugging.

## Advanced Topics

For detailed patterns and examples, see:
- [langgraph-patterns.md](langgraph-patterns.md) - State, nodes, routing, complete workflow examples
- [testing-agents.md](testing-agents.md) - Unit testing, integration testing, LLM-as-judge evaluation
- [prompt-engineering.md](prompt-engineering.md) - Prompt templates, agent-specific prompts

## Quick Reference

### Common Imports

```python
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
from typing import TypedDict, Annotated, Sequence, Optional
```

### Workflow Compilation

```python
# Compile and execute
app = workflow.compile()
result = await app.ainvoke(initial_state)
```

### Streaming with astream_events

```python
async for event in app.astream_events(state, version="v2"):
    if event["event"] == "on_chat_model_stream":
        yield event["data"]["chunk"].content
```
