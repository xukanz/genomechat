# Advanced Skill Authoring

This document covers testing, debugging, advanced techniques, and maintenance. For core concepts, see [SKILL.md](SKILL.md). For patterns and examples, see [patterns.md](patterns.md).

## Contents
- [Testing Your Skills](#testing-your-skills)
- [Skill Authoring Checklist](#skill-authoring-checklist)
- [Advanced Techniques](#advanced-techniques)
- [Maintenance and Evolution](#maintenance-and-evolution)

## Testing Your Skills

### Test Skill Discovery

After creating a skill:

1. **Check metadata loads**: Restart Claude Code and verify no errors
2. **Test automatic activation**: Ask questions matching your description
3. **Test explicit usage**: Request the skill by name
4. **Verify tool usage**: Ensure skill has necessary tools

### Example Test Queries

For `python-development` skill:
```
"How should I structure my pytest fixtures?"
"Show me error handling best practices"
"What's the right way to validate data with Pydantic?"
```

For `database-operations` skill:
```
"What's the naming convention for primary keys?"
"How do I set up a repository pattern?"
"Show me FastAPI endpoint documentation"
```

### Debug Skill Issues

**Skill not activating?**
- Add more trigger keywords to description
- Use phrases like "use proactively" or "MUST BE USED"
- Be more specific about when to use
- Test explicit invocation: "Use the [skill-name] skill"

**Skill activating incorrectly?**
- Make description more specific
- Differentiate from similar skills
- Add negative examples (when NOT to use)

**Skill has wrong content?**
- Review and refine based on usage
- Add more examples
- Clarify ambiguous sections
- Split if trying to do too much

## Skill Authoring Checklist

Before saving a new skill:

### Content Quality
- [ ] Description includes what, when, and triggers
- [ ] Examples are concrete and runnable
- [ ] Terminology is consistent throughout
- [ ] Anti-patterns shown alongside good patterns
- [ ] Content is under 500 lines (or split appropriately)

### Technical Requirements
- [ ] Name is lowercase with hyphens
- [ ] Name is under 64 characters
- [ ] Description is under 1024 characters
- [ ] No XML tags in frontmatter
- [ ] No reserved words in name

### Discoverability
- [ ] Trigger keywords match likely user queries
- [ ] Description is specific, not vague
- [ ] Clear about when to use vs when not to
- [ ] Differentiated from similar skills

### Testing
- [ ] Tested with automatic activation
- [ ] Tested with explicit invocation
- [ ] Verified in actual usage scenarios
- [ ] Team feedback incorporated

### Documentation
- [ ] Purpose clearly stated
- [ ] Examples provided for key concepts
- [ ] Links to related skills/docs included
- [ ] Maintenance notes if applicable

## Advanced Techniques

### Skill Composition

Reference other skills for related content:

```markdown
## Database Operations

For database testing patterns, see the testing-patterns skill.
For API endpoint design, see the api-development skill.

This skill focuses on database schema and repository patterns.
```

### Conditional Details

Show basic content, link to advanced:

```markdown
## Basic Usage

Simple CRUD operations:
```python
user = User.objects.get(id=123)
```

## Advanced Usage

For transaction management, see [advanced.md](advanced.md)
For query optimization, see [performance.md](performance.md)
```

### Script Integration

Include executable scripts:

```markdown
## Validation Script

Run the validation script before deployment:

```bash
python scripts/validate_config.py
```

The script checks:
- Environment variables set
- Database connections valid
- API endpoints reachable
```

**Note**: Scripts in `scripts/` directory should be executable, not loaded into context. Only their output enters the context window.

## Maintenance and Evolution

### Regular Review

Schedule quarterly skill reviews:
- Remove outdated content
- Add new best practices
- Update examples
- Merge duplicate information
- Split overgrown skills

### Version Notes

Document significant changes:

```markdown
## Changelog

### 2025-02 - Major Update
- Added three-level loading architecture
- Added security considerations
- Added cross-platform considerations

### 2024-11 - Initial Release
- Core skill authoring patterns
- Description guidelines
- Content organization
```

### Team Feedback Loop

Encourage team updates:

```bash
# When you learn something new
code .claude/skills/relevant-skill/SKILL.md

# Add new section or update existing
# Commit with descriptive message
git commit -m "docs(skills): add context manager pattern to python-development"

# Team gets improvement on next pull
git push
```

## Meta: This Skill

The skill-authoring skill itself follows these principles:
- **Focused**: Only about skill authoring
- **Progressive disclosure**: Core in SKILL.md, details in linked files
- **Example-driven**: Shows good vs bad patterns
- **Actionable**: Provides checklists and workflows
- **Self-referential**: Demonstrates its own advice

Use this skill as a template for quality and structure.
