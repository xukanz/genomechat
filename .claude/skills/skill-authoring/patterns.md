# Skill Patterns and Best Practices

This document contains detailed patterns and best practices for authoring effective skills. For core concepts, see [SKILL.md](SKILL.md).

## Contents
- [Common Patterns](#common-patterns)
- [Best Practices](#best-practices)
- [Anti-Patterns to Avoid](#anti-patterns-to-avoid)

## Common Patterns

### Template Pattern

Provide templates for consistent output:

````markdown
## Commit Message Template

ALWAYS use this format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: feat, fix, docs, style, refactor, test, chore

Example:
```
feat(auth): add JWT authentication

- Implement token generation
- Add refresh token support
- Update user model

Closes #123
```
````

### Examples Pattern

Show concrete input/output pairs:

````markdown
## Function Naming

**Example 1:**
```python
# ❌ Bad: Vague name
def process():
    pass

# ✅ Good: Descriptive name
def validate_user_email():
    pass
```

**Example 2:**
```python
# ❌ Bad: Inconsistent naming
def getUserData():  # camelCase
    pass

# ✅ Good: Consistent style
def get_user_data():  # snake_case
    pass
```
````

### Conditional Workflow Pattern

Guide through decision points:

```markdown
## File Operation Workflow

1. Determine the operation type:

   **Reading existing file?** → Use Read tool
   **Editing existing file?** → Use Edit tool
   **Creating new file?** → Use Write tool

2. For Read operations:
   - Check file exists first
   - Use appropriate encoding
   - Handle large files with streaming

3. For Edit operations:
   - Read file first to see content
   - Use exact string matching
   - Verify changes after edit
```

### Checklist Pattern

For multi-step processes:

```markdown
## Code Review Checklist

Copy and track progress:

```
Review Progress:
- [ ] Security: No exposed secrets or vulnerabilities
- [ ] Correctness: Logic is sound, edge cases handled
- [ ] Performance: No obvious bottlenecks
- [ ] Tests: Critical paths covered
- [ ] Documentation: Public APIs documented
```

Complete each item systematically.
```

## Best Practices

### 1. Start with Claude Generation

**Recommended workflow**:
```bash
# Let Claude draft the skill first
"Create a skill for [topic] that covers [aspects]"

# Review Claude's output
# Customize to match your team's style
# Add project-specific examples
# Save and test
```

This gives you a solid foundation.

### 2. Iterate Based on Usage

**Continuous improvement cycle**:
1. Create initial skill
2. Use in real scenarios
3. Notice gaps or confusion
4. Update skill with improvements
5. Repeat

**Example iteration**:
```bash
# Initial version: Basic testing patterns
git commit -m "feat(skills): add testing-patterns skill"

# After usage: Add async testing
git commit -m "docs(skills): add async testing patterns to testing-patterns"

# After review: Add mocking examples
git commit -m "docs(skills): add comprehensive mocking examples to testing-patterns"
```

### 3. Make Examples Runnable

**✅ Good** (complete, runnable):
```python
import pytest
from datetime import datetime
from myapp.models import User

@pytest.fixture
def sample_user():
    return User(
        id=123,
        email="test@example.com",
        created_at=datetime.now()
    )

def test_user_creation(sample_user):
    assert sample_user.email == "test@example.com"
```

**❌ Bad** (incomplete, pseudocode):
```python
# Create a user fixture
@pytest.fixture
def user():
    # return user
```

### 4. Use Visual Hierarchy

Make content scannable:

```markdown
# Main Topic

## Major Section

### Subsection

**Bold for emphasis**
- Bullet points for lists
- Keep related items together

`code` for technical terms
```

### 5. Include Anti-Patterns

Show what NOT to do:

```markdown
## Error Handling

**❌ Bad** (swallows errors):
```python
try:
    process_data()
except:
    pass  # Silent failure
```

**✅ Good** (explicit handling):
```python
try:
    process_data()
except ValueError as e:
    logger.error(f"Invalid data: {e}")
    raise
```
```

## Anti-Patterns to Avoid

### 1. Too Broad

**❌ Problem**:
```yaml
name: programming
description: Help with programming tasks
```

**✅ Solution**: Split into focused skills
- `python-development`
- `javascript-patterns`
- `api-design`

### 2. Too Narrow

**❌ Problem**:
```yaml
name: sort-lists-alphabetically
description: Sort Python lists alphabetically
```

**✅ Solution**: Combine into broader skill
- Part of `python-development` skill

### 3. Missing Triggers

**❌ Problem**:
```yaml
description: Database patterns and best practices
```

**✅ Solution**: Add explicit triggers
```yaml
description: Database naming standards, repository patterns, model-database alignment, and API route conventions. Use when working with databases, creating models, implementing repositories, or designing API endpoints.
```

### 4. Explaining Basics

**❌ Problem**:
```markdown
## What is Git?
Git is a version control system that tracks changes...
```

**✅ Solution**: Assume knowledge, provide specific context
```markdown
## Git Workflow
This project uses GitHub Flow:
- Main branch is protected
- Feature branches from main
- PRs require review
```

### 5. Inconsistent Style

**❌ Problem**:
- Some examples use tabs, others spaces
- Mix of British/American spelling
- Inconsistent code comment style

**✅ Solution**: Establish and follow conventions
- Always 4 spaces for Python
- American spelling
- Comments start with capital letter
