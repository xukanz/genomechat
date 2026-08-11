---
name: skill-authoring
description: Expert guide for creating and authoring effective Claude Code Agent Skills. Use when creating new skills, writing skill documentation, improving skill descriptions, organizing skill content, or learning skill best practices. Triggers on skill creation, skill authoring, writing skills, skill best practices.
---

# Agent Skill Authoring Guide

## Philosophy: Skills as Living Documentation

Skills are **living documentation** that capture and evolve with team knowledge. They should:
- Reflect current best practices, not just initial documentation
- Update when you discover better approaches
- Capture solutions to tricky problems
- Serve as team memory that improves over time

**Core Principle**: Concise is key. Assume Claude is smart - only add context Claude doesn't already have.

## How Skills Work: Three-Level Loading

Skills use **progressive disclosure** - Claude loads information in stages as needed, rather than consuming context upfront.

### Level 1: Metadata (Always Loaded)

The YAML frontmatter provides discovery information (~100 tokens per Skill):

```yaml
---
name: pdf-processing
description: Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files.
---
```

Claude loads all skill metadata at startup. This lightweight approach means many Skills can be installed without context penalty.

### Level 2: Instructions (Loaded When Triggered)

The main body of SKILL.md contains procedural knowledge (aim for under 5k tokens):

```markdown
# PDF Processing

## Quick start
Use pdfplumber to extract text...

For advanced form filling, see [FORMS.md](FORMS.md).
```

When a request matches a Skill's description, Claude reads SKILL.md via bash. Only then does this content enter the context window.

### Level 3: Resources (Loaded As Needed)

Additional files are accessed only when referenced (effectively unlimited):

```
pdf-skill/
├── SKILL.md          # Main instructions
├── FORMS.md          # Form-filling guide
├── REFERENCE.md      # API reference
└── scripts/
    └── fill_form.py  # Utility script (runs via bash, code never enters context)
```

| Level | When Loaded | Token Cost | Content |
|-------|-------------|------------|---------|
| **Level 1: Metadata** | Always (at startup) | ~100 tokens per Skill | `name` and `description` from YAML |
| **Level 2: Instructions** | When Skill is triggered | Under 5k tokens | SKILL.md body |
| **Level 3: Resources** | As needed | Effectively unlimited | Bundled files, scripts executed via bash |

**Key insight**: Scripts run via bash - only their output enters context, not their code.

## When to Create a New Skill

### Create a skill when:
- ✅ Topic is self-contained and focused
- ✅ Content would be useful across multiple sessions
- ✅ Clear triggering keywords exist
- ✅ Pattern is reusable by team
- ✅ Would otherwise bloat CLAUDE.md
- ✅ Represents specialized domain knowledge

### Don't create a skill for:
- ❌ One-time project-specific tasks
- ❌ Content already in PROJECT.md
- ❌ Overly broad topics (split them instead)
- ❌ Information Claude already knows

## Skill Structure and Requirements

### File Format

```markdown
---
name: skill-name
description: What the skill does and when to use it with trigger keywords
---

# Skill Name

## Purpose

Brief explanation of when and why to use this skill.

## Content Sections

Organized, focused content with examples...
```

### YAML Frontmatter Requirements

**name** field:
- **Required**: Yes
- **Format**: lowercase letters, numbers, and hyphens only
- **Max length**: 64 characters
- **No XML tags**: Cannot contain `<` or `>`
- **No reserved words**: Cannot contain "anthropic" or "claude"

**description** field:
- **Required**: Yes
- **Format**: Natural language with trigger keywords
- **Max length**: 1024 characters
- **No XML tags**: Cannot contain `<` or `>`
- **Critical for discovery**: Claude uses this to decide when to use the skill

## Writing Effective Descriptions

The description is **the most important field** for skill discovery. Claude reads all skill descriptions at startup to decide which skills to load.

### Anatomy of a Good Description

```yaml
description: [What it does], [when to use it]. [Trigger keywords].
```

**Three components**:
1. **What**: Clear statement of skill's purpose
2. **When**: Specific scenarios for activation
3. **Triggers**: Keywords that match user queries

### Examples

**✅ Excellent** (specific, includes triggers):
```yaml
description: Database naming standards, repository patterns, model-database alignment, and API route conventions. Use when working with databases, creating models, implementing repositories, or designing API endpoints.
```

**❌ Bad** (too vague, no triggers):
```yaml
description: Helps with databases
```

### Trigger Keyword Strategy

Include keywords users would naturally mention:

**For python-development**:
- Direct: pytest, pydantic, testing, error handling
- Contextual: "write a test", "validate data", "handle errors"
- Related: fixtures, validation, exceptions

**Pro tip**: Think about how users would phrase questions, then include those words.

## Content Organization

### Keep SKILL.md Under 500 Lines

When approaching this limit:
1. **Split into multiple files** using progressive disclosure
2. **Link to additional files** from SKILL.md
3. **Use one level of nesting** (don't go deeper)

**Example structure**:
```
skill-name/
├── SKILL.md              # Main overview (< 500 lines)
├── advanced.md           # Advanced patterns
├── examples.md           # Detailed examples
└── scripts/              # Utility scripts
    └── helper.py
```

### Progressive Disclosure Pattern

SKILL.md serves as table of contents with links to detailed content:

````markdown
# Skill Name

## Quick Start
[Essential info here - 20-50 lines]

## Advanced Usage
For detailed patterns, see [advanced.md](advanced.md)
````

## Content Guidelines

### 1. Assume Claude is Smart

Only add what Claude doesn't have. Skip explanations of basic concepts.

**❌ Bad**: "A database is a structured collection of data..."
**✅ Good**: "This project uses PostgreSQL with entity-specific primary keys: `{entity}_id`"

### 2. Show, Don't Tell

Use concrete examples instead of abstract descriptions.

### 3. Use Consistent Terminology

Pick one term and stick with it throughout.

### 4. Avoid Time-Sensitive Information

Use versioning sections instead of dates that will become stale.

### 5. Provide Templates for Output

For strict requirements, use exact templates. For flexible guidance, show adaptable formats.

For detailed patterns and examples, see [patterns.md](patterns.md).

## Security Considerations

Use Skills only from **trusted sources**: those you created yourself or obtained from Anthropic. Skills can direct Claude to invoke tools or execute code, so malicious Skills pose real risks.

### Key Security Risks

- **Tool misuse**: Malicious Skills can invoke tools (file operations, bash commands, code execution) in harmful ways
- **Data exposure**: Skills with access to sensitive data could leak information to external systems
- **External sources**: Skills that fetch data from external URLs are risky—fetched content may contain malicious instructions

### Before Using Third-Party Skills

**Audit thoroughly**:
- Review all files: SKILL.md, scripts, images, and other resources
- Look for unusual patterns: unexpected network calls, file access, or operations that don't match the Skill's stated purpose

**Treat like installing software**: Only use Skills from trusted sources, especially in production systems with sensitive data.

## Cross-Platform Considerations

Skills have different behaviors depending on where they run:

### Claude Code (This Environment)
- **Location**: Personal (`~/.claude/skills/`) or project-based (`.claude/skills/`)
- **Network**: Full access (same as any program on your computer)
- **Sharing**: Via git repositories or Claude Code Plugins
- **Packages**: Avoid global installation; use local/virtual environments

### Claude API
- **Network**: No external API calls or internet access
- **Packages**: Only pre-installed packages available
- **Sharing**: Workspace-wide via Skills API

### Claude.ai
- **Network**: Varies by user/admin settings (full, partial, or none)
- **Sharing**: Individual user only; no org-wide distribution
- **Upload**: Via Settings > Features as zip files

**Important**: Skills do NOT sync across surfaces. A Skill uploaded to Claude.ai must be separately uploaded to the API, and Claude Code Skills are filesystem-based.

## Quick Reference

### Creating a Skill

```bash
mkdir -p .claude/skills/skill-name
cat > .claude/skills/skill-name/SKILL.md << 'EOF'
---
name: skill-name
description: What it does, when to use it, trigger keywords
---

# Skill Name

Content here...
EOF
```

### Testing a Skill

```bash
# Restart Claude Code to load new skill
# Ask questions matching description
# Verify activation and behavior
```

### Skill Quality Metrics

Good skills have:
- Clear, specific description with triggers
- Concrete, runnable examples
- Under 500 lines (or well-organized splits)
- Consistent terminology
- Regular updates based on usage

## Additional Resources

**Detailed Guides** (in this skill):
- [patterns.md](patterns.md) - Common patterns, best practices, anti-patterns
- [advanced.md](advanced.md) - Testing, debugging, checklists, maintenance

**Official Documentation**:
- [Anthropic Engineering Blog: Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills)
- [Agent Skills API Guide](https://docs.anthropic.com/en/build-with-claude/skills-guide)
- [Skills Cookbook](https://platform.claude.com/cookbook/skills-notebooks-01-skills-introduction)

**Project Resources**:
- [CLAUDE.md](../../../CLAUDE.md) - Project quick reference
- Other skills in `.claude/skills/` - Examples to learn from

---

**Remember**: Skills are living documentation. Update this skill when you discover better skill authoring practices!
