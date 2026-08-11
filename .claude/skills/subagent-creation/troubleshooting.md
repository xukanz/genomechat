# Subagent Troubleshooting

Common issues and solutions. For setup, see [SKILL.md](SKILL.md).

## Agent Not Being Used Automatically

**Symptoms**: Claude doesn't delegate to your subagent when it should.

**Solutions**:
- Add more trigger keywords to description
- Use phrases like "use proactively" or "MUST BE USED"
- Be more specific about when to use
- Test with explicit invocation first

**Example fix**:
```markdown
# Before (vague)
description: Helps with code review

# After (specific with triggers)
description: Expert code reviewer. Use proactively after any code changes to review quality, security, and maintainability. Triggers on code review, quality check, security audit, PR review.
```

## Agent Lacks Necessary Context

**Symptoms**: Agent doesn't understand the codebase or task.

**Solutions**:
- Provide more context in initial prompt
- Grant Read tool for context gathering
- Reference specific files or functions
- Add more detailed system prompt with examples

**Example**:
```bash
# Less effective
Use code-reviewer to check my code

# More effective
Use code-reviewer to review the authentication changes in backend/src/auth/
```

## Agent Has Wrong Tools

**Symptoms**: Agent can't perform necessary actions.

**Solutions**:
- Use `/agents` to edit tool access
- Review what tools agent actually needs
- Remove unnecessary tools for focus

**Common tool needs**:
| Agent Type | Typical Tools |
|------------|---------------|
| Reviewer | Read, Grep, Glob, Bash |
| Fixer | Read, Edit, Bash, Grep |
| Writer | Read, Write, Grep, Glob |
| Analyst | Bash, Read, Write |

## Agent Produces Incorrect Results

**Symptoms**: Agent output doesn't match expectations.

**Solutions**:
- Review and refine system prompt
- Add more examples and constraints
- Test with various scenarios
- Consider model selection (opus vs sonnet vs haiku)

**Model selection guide**:
- **opus**: Complex reasoning, detailed analysis
- **sonnet**: Balanced capability and speed (default)
- **haiku**: Fast, simple tasks, economical

## Agent Not Found

**Symptoms**: Error that agent doesn't exist.

**Solutions**:
- Check file location (`.claude/agents/` or `~/.claude/agents/`)
- Verify filename matches agent name
- Ensure YAML frontmatter is valid
- Check for typos in agent name

**File structure check**:
```bash
ls -la .claude/agents/
# Should show your-agent-name.md
```

## Subagent Creation Checklist

Before troubleshooting, verify:

- [ ] Clear, focused purpose
- [ ] Unique name (lowercase-with-hyphens)
- [ ] Descriptive description with trigger keywords
- [ ] Appropriate tool access (minimal necessary)
- [ ] Detailed system prompt with examples
- [ ] Model selection appropriate for task
- [ ] Location chosen (project vs user)
- [ ] Tested with sample scenarios
