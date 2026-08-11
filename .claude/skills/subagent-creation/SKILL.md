---
name: subagent-creation
description: Create and manage Claude Code subagents for specialized workflows. Use when creating custom subagents, defining agent configurations, managing agent tools, or designing task-specific AI assistants. Triggers on subagent, /agents, agent creation, agent tools.
---

# Claude Code Subagent Creation

## What are Subagents?

Subagents are specialized AI assistants in Claude Code that:
- Have specific purposes and expertise areas
- Use separate context windows from main conversation
- Can be configured with specific tools
- Include custom system prompts guiding behavior

**Key Benefits**:
- **Context preservation**: Each subagent operates independently
- **Specialized expertise**: Fine-tuned for specific domains
- **Reusability**: Share subagents across projects and teams
- **Flexible permissions**: Granular tool access control

## Quick Start

### Using /agents Command (Recommended)

```bash
# Open subagents interface
/agents

# Then:
# 1. Select 'Create New Agent'
# 2. Choose project or user level
# 3. Generate with Claude (recommended) or write manually
# 4. Customize tools and permissions
# 5. Save and use
```

### Manual Creation

```bash
# Project subagent (shared with team)
mkdir -p .claude/agents
cat > .claude/agents/my-agent.md << 'EOF'
---
name: my-agent
description: Clear description of when to use. Include trigger keywords.
tools: Read, Edit, Bash, Grep, Glob  # Optional
model: sonnet  # Optional
---

Your agent's system prompt goes here.
Define the agent's role, capabilities, and approach.
EOF

# User subagent (available across all projects)
mkdir -p ~/.claude/agents
```

## Configuration

### File Locations and Priority

| Type | Location | Scope | Priority |
|------|----------|-------|----------|
| **Project** | `.claude/agents/` | Current project | Highest |
| **User** | `~/.claude/agents/` | All projects | Medium |
| **Plugin** | Plugin `agents/` dir | Plugin-specific | Lower |
| **CLI** | `--agents` flag | Session-specific | Lowest |

### Configuration Fields

```markdown
---
name: agent-name                    # Required: lowercase-with-hyphens
description: When to use this agent # Required: Natural language + keywords
tools: tool1, tool2, tool3          # Optional: Specific tools or omit for all
model: sonnet                       # Optional: sonnet, opus, haiku, inherit
---

System prompt content...
```

#### Field Details

**name** (Required):
- Lowercase letters and hyphens only
- Must be unique within scope
- Examples: `code-reviewer`, `test-runner`, `data-analyst`

**description** (Required):
- Natural language description
- Include trigger keywords for automatic invocation
- Use "proactively" or "MUST BE USED" for automatic delegation

**tools** (Optional):
- Comma-separated list of tool names
- If omitted: inherits all tools from main thread
- If specified: restricted to listed tools only

**model** (Optional):
- `sonnet`: Claude Sonnet (default)
- `opus`: Claude Opus (most capable)
- `haiku`: Claude Haiku (fastest)
- `inherit`: Use same model as main conversation

### Available Tools

Common tools for subagents:
- **Read**: Read file contents
- **Edit**: Edit existing files
- **Write**: Create new files
- **Bash**: Execute shell commands
- **Grep**: Search code patterns
- **Glob**: Find files by pattern
- **Task**: Launch other specialized agents
- **WebFetch**: Fetch web content
- **MCP Tools**: Any tools from configured MCP servers

Use `/agents` command to see complete tool list.

## Using Subagents

### Automatic Delegation

Claude automatically uses subagents when:
- Task matches agent description
- Agent has appropriate tools
- Context suggests agent expertise

**Encourage proactive use** by adding keywords to description:
- "Use proactively after..."
- "MUST BE USED when..."
- "Automatically trigger on..."

### Explicit Invocation

```bash
# Request specific agent
Use the code-reviewer subagent to check my changes

# Chain multiple agents
First use data-analyst to query the data, then use doc-writer to document findings

# Resume previous agent session
Resume agent abc123 and continue the analysis
```

## Managing Subagents

### View All Subagents

```bash
/agents
```

Shows built-in, user, project, and plugin subagents.

### Edit Subagent

```bash
# Via interface
/agents → Select agent → Edit

# Or directly edit file
code .claude/agents/agent-name.md
```

### Delete Subagent

```bash
# Via interface
/agents → Select agent → Delete

# Or remove file
rm .claude/agents/agent-name.md
```

## Quick Design Tips

### Focused Subagents

✅ **Good**: `test-runner`, `code-reviewer`, `sql-optimizer`
❌ **Bad**: `helper`, `general-purpose`

### Detailed Prompts

Include: Role, When to use, Process, Best practices, Output format, Examples

### Minimal Tools

Only grant necessary tools:
```markdown
# Code reviewer doesn't need Write
tools: Read, Grep, Glob, Bash

# Test runner needs edit capability
tools: Read, Edit, Bash, Grep
```

## Additional Resources

For detailed patterns and examples, see:
- [example-subagents.md](example-subagents.md) - Ready-to-use templates (code-reviewer, test-runner, debugger, data-analyst, doc-writer)
- [advanced-patterns.md](advanced-patterns.md) - Resumable agents, CLI config, performance, version control
- [troubleshooting.md](troubleshooting.md) - Common issues and solutions

## Quick Checklist

Before creating a subagent:
- [ ] Clear, focused purpose
- [ ] Unique name (lowercase-with-hyphens)
- [ ] Descriptive description with trigger keywords
- [ ] Appropriate tool access (minimal necessary)
- [ ] Detailed system prompt with examples
- [ ] Tested with sample scenarios
