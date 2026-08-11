# Advanced Subagent Patterns

Advanced usage patterns for Claude Code subagents. For basics, see [SKILL.md](SKILL.md).

## Contents
- [Resumable Subagents](#resumable-subagents)
- [CLI Configuration](#cli-configuration)
- [Performance Optimization](#performance-optimization)
- [Version Control](#version-control)
- [Best Practices](#best-practices)

## Resumable Subagents

Subagents can be resumed to continue previous work:

```bash
# Initial invocation returns agentId
Use code-analyzer to review authentication module
# Returns: agentId "abc123"

# Resume the agent later
Resume agent abc123 and now check authorization logic
```

**Use cases**:
- Long-running research across sessions
- Iterative refinement with context
- Multi-step workflows maintaining context

**How it works**:
- Each agent execution gets unique `agentId`
- Conversation stored in `agent-{agentId}.jsonl`
- Resume with full previous context
- No duplicate messages recorded

## CLI Configuration

For session-specific or testing:

```bash
claude --agents '{
  "quick-reviewer": {
    "description": "Fast code review",
    "prompt": "Review code quickly for obvious issues",
    "tools": ["Read", "Grep"],
    "model": "haiku"
  }
}'
```

**Use cases**:
- Testing agent configurations
- Session-specific agents
- Automation scripts
- Documentation examples

## Performance Optimization

**Context efficiency**:
- ✅ Subagents preserve main context
- ✅ Longer overall sessions possible
- ✅ Focused context per subagent

**Latency considerations**:
- ⚠️ Subagents start with clean slate
- ⚠️ May need to gather context
- ⚠️ Additional overhead per invocation

**Optimization tips**:
- Provide context in initial prompt
- Reference specific files/functions
- Use explicit invocation when appropriate
- Cache frequently needed context in prompt

## Version Control

```bash
# Commit project agents
git add .claude/agents/
git commit -m "feat(agents): add code-reviewer subagent"
git push

# Team gets agents automatically
git pull
```

## Best Practices

### 1. Start with Claude Generation

**Recommended workflow**:
```bash
/agents
→ Create New Agent
→ Generate with Claude (describe your needs)
→ Review and customize
→ Save
```

### 2. Design Focused Subagents

✅ **Good** (focused):
- `test-runner`: Runs tests and fixes failures
- `code-reviewer`: Reviews code quality
- `sql-optimizer`: Optimizes database queries

❌ **Bad** (too broad):
- `helper`: Does everything
- `general-purpose`: Handles all tasks

### 3. Write Detailed Prompts

Include:
- **Role**: Who the agent is
- **When to use**: Triggering conditions
- **Process**: Step-by-step approach
- **Best practices**: Guidelines to follow
- **Output format**: How to present results
- **Examples**: Concrete demonstrations

### 4. Limit Tool Access

Only grant necessary tools:

```markdown
# Code reviewer doesn't need Write
tools: Read, Grep, Glob, Bash

# Test runner needs edit capability
tools: Read, Edit, Bash, Grep

# Documentation writer needs file creation
tools: Read, Write, Grep, Glob
```

### 5. Descriptive Names and Keywords

```markdown
---
name: security-auditor
description: Security audit specialist. Use proactively after code changes for security review. Triggers on security, audit, vulnerability, authentication, authorization, secrets, injection, XSS, CSRF.
---
```

More keywords = better automatic delegation!
