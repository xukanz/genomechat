"""Prompt template processing utilities."""

import logging
import os
import re
from datetime import datetime
from typing import Dict, Any

from langchain_core.prompts import PromptTemplate

from src.config.research_mode import ResearchModeType

logger = logging.getLogger(__name__)


def get_prompt_template(prompt_name: str) -> str:
    """Load prompt template from markdown file.

    Supports subdirectory prompts (e.g., "sql_agent/react_sql_generator").

    Args:
        prompt_name: Name of the prompt file (without .md extension).
                     Can include subdirectory path separated by "/".

    Returns:
        Template string (raw, not processed)
    """
    # Handle subdirectory prompts (e.g., "sql_agent/react_sql_generator")
    if "/" in prompt_name:
        template_path = os.path.join(os.path.dirname(__file__), f"{prompt_name}.md")
    else:
        template_path = os.path.join(os.path.dirname(__file__), f"{prompt_name}.md")

    template = open(template_path).read()
    return template


def process_conditional_sections(
    template: str, research_mode: ResearchModeType = "standard"
) -> str:
    """Process conditional sections in template based on research_mode.

    Supports Jinja2-style conditionals:
    - {%- if research_mode == "deep_research" %} ... {%- endif %}
    - {%- if research_mode == "deep_research" %} ... {%- else %} ... {%- endif %}
    - {%- if research_mode == "standard" %} ... {%- endif %}

    Args:
        template: Raw template string with conditional sections
        research_mode: Research mode to use for conditional processing

    Returns:
        Template with conditional sections processed
    """
    if research_mode == "deep_research":
        # Keep deep research sections, remove standard sections

        # Handle: {%- if research_mode == "deep_research" %} ... {%- else %} ... {%- endif %}
        # Keep the if part, remove else and endif
        template = re.sub(
            r'({%-\s*if\s+research_mode\s*==\s*"deep_research"\s*%})(.*?){%-\s*else\s*%}.*?{%-\s*endif\s*%}',
            r"\1\2",
            template,
            flags=re.DOTALL,
        )

        # Handle: {%- if research_mode == "standard" %} ... {%- else %} ... {%- endif %}
        # Remove the if part, keep else part, remove endif
        template = re.sub(
            r'{%-\s*if\s+research_mode\s*==\s*"standard"\s*%}.*?{%-\s*else\s*%}(.*?){%-\s*endif\s*%}',
            r"\1",
            template,
            flags=re.DOTALL,
        )

        # Handle standalone: {%- if research_mode == "deep_research" %} ... {%- endif %}
        # Keep content, remove markers
        template = re.sub(
            r'{%-\s*if\s+research_mode\s*==\s*"deep_research"\s*%}(.*?){%-\s*endif\s*%}',
            r"\1",
            template,
            flags=re.DOTALL,
        )

        # Remove standalone standard sections: {%- if research_mode == "standard" %} ... {%- endif %}
        template = re.sub(
            r'{%-\s*if\s+research_mode\s*==\s*"standard"\s*%}.*?{%-\s*endif\s*%}',
            "",
            template,
            flags=re.DOTALL,
        )

    else:
        # Keep standard sections, remove deep research sections

        # Handle: {%- if research_mode == "standard" %} ... {%- else %} ... {%- endif %}
        # Keep the if part, remove else and endif
        template = re.sub(
            r'({%-\s*if\s+research_mode\s*==\s*"standard"\s*%})(.*?){%-\s*else\s*%}.*?{%-\s*endif\s*%}',
            r"\1\2",
            template,
            flags=re.DOTALL,
        )

        # Handle: {%- if research_mode == "deep_research" %} ... {%- else %} ... {%- endif %}
        # Remove the if part, keep else part, remove endif
        template = re.sub(
            r'{%-\s*if\s+research_mode\s*==\s*"deep_research"\s*%}.*?{%-\s*else\s*%}(.*?){%-\s*endif\s*%}',
            r"\1",
            template,
            flags=re.DOTALL,
        )

        # Handle standalone: {%- if research_mode == "standard" %} ... {%- endif %}
        # Keep content, remove markers
        template = re.sub(
            r'{%-\s*if\s+research_mode\s*==\s*"standard"\s*%}(.*?){%-\s*endif\s*%}',
            r"\1",
            template,
            flags=re.DOTALL,
        )

        # Remove standalone deep research sections: {%- if research_mode == "deep_research" %} ... {%- endif %}
        template = re.sub(
            r'{%-\s*if\s+research_mode\s*==\s*"deep_research"\s*%}.*?{%-\s*endif\s*%}',
            "",
            template,
            flags=re.DOTALL,
        )

    return template


def get_processed_prompt(
    prompt_name: str,
    template_vars: Dict[str, Any] | None = None,
    research_mode: ResearchModeType = "standard",
) -> str:
    """Get processed prompt text with template variables substituted.

    Args:
        prompt_name: Name of the prompt file (without .md extension)
        template_vars: Dictionary of template variables to substitute
        research_mode: Research mode for conditional section processing

    Returns:
        Processed prompt string
    """
    if template_vars is None:
        template_vars = {}

    # Add common template variables
    full_template_vars = {
        "CURRENT_TIME": datetime.now().strftime("%a %b %d %Y %H:%M:%S %z"),
        **template_vars,
    }

    # Handle empty values by replacing with empty string
    for key, value in full_template_vars.items():
        if value is None or (isinstance(value, str) and value.strip() == ""):
            full_template_vars[key] = ""

    # Load raw template
    template = get_prompt_template(prompt_name)

    # Process conditional sections based on research_mode
    template = process_conditional_sections(template, research_mode)

    # Escape curly braces using backslash (for LangChain template processing)
    template = template.replace("{", "{{").replace("}", "}}")
    # Replace `<<VAR>>` with `{VAR}` (our custom template variable syntax)
    template = re.sub(r"<<([^>>]+)>>", r"{\1}", template)

    prompt = PromptTemplate(
        input_variables=list(full_template_vars.keys()),
        template=template,
    ).format(**full_template_vars)

    return prompt


def get_database_context_vars() -> Dict[str, str]:
    """Get template variables for database context injection.

    Retrieves the active database profile and returns template variables
    for dynamic prompt injection.

    Returns:
        Dictionary with database context variables:
        - DATABASE_NAME: Internal name (e.g., "clinvar", "gwas")
        - DATABASE_DISPLAY_NAME: Display name (e.g., "ClinVar", "GWAS Catalog")
        - DATABASE_TYPE: Database type (e.g., "sqlite", "duckdb")
        - DATABASE_DESCRIPTION: Description of the database
        - SQL_DIALECT: SQL dialect (e.g., "SQLite", "PostgreSQL")
        - SQL_DIALECT_NOTES: Dialect-specific notes for query generation
    """
    try:
        from src.config.database_registry import get_active_profile_from_context

        profile = get_active_profile_from_context()
    except Exception as e:
        logger.warning(f"Failed to get active database profile: {e}. Using defaults.")
        return {
            "DATABASE_NAME": "clinvar",
            "DATABASE_DISPLAY_NAME": "ClinVar",
            "DATABASE_TYPE": "sqlite",
            "DATABASE_DESCRIPTION": (
                "NCBI ClinVar: human genetic variants with their reported clinical "
                "significance and associated conditions"
            ),
            "SQL_DIALECT": "SQLite",
            "SQL_DIALECT_NOTES": "",
        }

    # Map database type to display dialect name
    dialect_map = {
        "sqlite": "SQLite",
        "postgresql": "PostgreSQL",
        "duckdb": "PostgreSQL",  # DuckDB uses PostgreSQL syntax
        "mysql": "MySQL",
    }

    sql_dialect = dialect_map.get(profile.sql_dialect, profile.sql_dialect)

    # Generate dialect-specific notes
    dialect_notes = _get_sql_dialect_notes(profile.sql_dialect)

    return {
        "DATABASE_NAME": profile.name,
        "DATABASE_DISPLAY_NAME": profile.display_name,
        "DATABASE_TYPE": profile.database_type,
        "DATABASE_DESCRIPTION": profile.description,
        "SQL_DIALECT": sql_dialect,
        "SQL_DIALECT_NOTES": dialect_notes,
    }


def _get_sql_dialect_notes(dialect: str) -> str:
    """Get SQL dialect-specific notes for query generation.

    Args:
        dialect: SQL dialect name ("sqlite", "postgresql")

    Returns:
        Markdown notes section for the dialect
    """
    if dialect == "postgresql":
        return """
**PostgreSQL/DuckDB SQL Notes:**
- Type casting: Use `CAST(x AS TYPE)` or `x::TYPE` syntax
- String functions: `LENGTH()`, `SUBSTRING()`, `CONCAT()`
- Array functions: `ARRAY_AGG()`, `STRING_AGG()`
- Use `DISTINCT ON (column)` for deduplication
- Window functions are fully supported
- Date functions: `DATE_TRUNC()`, `EXTRACT()`
"""
    elif dialect == "sqlite":
        return """
**SQLite SQL Notes:**
- Type casting: Use `CAST(x AS TYPE)` syntax
- String functions: `LENGTH()`, `SUBSTR()`, `||` for concatenation
- Use `GROUP_CONCAT()` for string aggregation
- No `DISTINCT ON` - use subqueries with GROUP BY
- Date functions: `strftime()`, `date()`, `time()`
- A boolean expression evaluates to 1/0, so `SUM(col = 'x')` counts matches
"""
    elif dialect == "mysql":
        return """
**MySQL SQL Notes:**
- Identifiers are quoted with backticks, not double quotes
- Use `LIMIT n` (no `FETCH FIRST`); `LIMIT offset, n` for paging
- String functions: `LENGTH()`, `SUBSTRING()`, `CONCAT()` (`||` is OR, not concat)
- Use `GROUP_CONCAT()` for string aggregation
- Regex matching via `REGEXP`
- This profile queries a shared public server: always bound results with
  `LIMIT` and filter on indexed columns rather than scanning large tables
"""
    return ""


def get_processed_prompt_with_database_context(
    prompt_name: str,
    template_vars: Dict[str, Any] | None = None,
    research_mode: ResearchModeType = "standard",
) -> str:
    """Get processed prompt with automatic database context injection.

    This is the preferred function for prompts that need database context.
    It automatically injects database-specific variables from the active profile.

    Args:
        prompt_name: Name of the prompt file (without .md extension)
        template_vars: Additional template variables to substitute
        research_mode: Research mode for conditional section processing

    Returns:
        Processed prompt string with database context
    """
    if template_vars is None:
        template_vars = {}

    # Get database context and merge with provided vars
    db_context = get_database_context_vars()
    merged_vars = {**db_context, **template_vars}

    return get_processed_prompt(prompt_name, merged_vars, research_mode)


def format_snippets_for_prompt(snippets: list[dict] | None) -> str:
    """Format project snippets for injection into coder prompt.

    Filters to enabled snippets only and formats each as a markdown code block
    with name, category, and description.

    Args:
        snippets: List of snippet dictionaries from project

    Returns:
        Formatted markdown string for prompt injection
    """
    if not snippets:
        return "_No project-specific snippets configured._"

    # Filter to enabled snippets only
    enabled_snippets = [s for s in snippets if s.get("enabled", True)]
    if not enabled_snippets:
        return "_No enabled snippets._"

    sections = []
    for snippet in enabled_snippets:
        # Build snippet section
        header = f"### {snippet['name']}"
        category = f"**Category**: {snippet.get('category', 'custom')}"

        parts = [header, category]

        if snippet.get("description"):
            parts.append(f"**Description**: {snippet['description']}")

        parts.append("")  # Empty line before code
        parts.append(f"```python\n{snippet['code']}\n```")

        sections.append("\n".join(parts))

    return "\n\n---\n\n".join(sections)
