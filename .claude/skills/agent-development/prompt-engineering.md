# Agent Prompt Engineering

Patterns for creating effective agent prompts. For core concepts, see [SKILL.md](SKILL.md).

## Contents
- [Prompt Template Structure](#prompt-template-structure)
- [Agent-Specific Prompts](#agent-specific-prompts)
- [Loading Agent Prompts](#loading-agent-prompts)

## Prompt Template Structure

Located in `src/prompts/template.py`:

```python
from typing import Dict, List
from langchain_core.prompts import ChatPromptTemplate

def create_agent_prompt(
    role: str,
    capabilities: List[str],
    constraints: List[str],
    examples: List[Dict[str, str]]
) -> ChatPromptTemplate:
    """
    Create structured agent prompt.

    Args:
        role: Agent's primary role description
        capabilities: List of agent capabilities
        constraints: List of operational constraints
        examples: Example interactions

    Returns:
        Configured chat prompt template
    """
    system_template = f"""You are a {role}.

Capabilities:
{chr(10).join(f"- {cap}" for cap in capabilities)}

Constraints:
{chr(10).join(f"- {constraint}" for constraint in constraints)}

Examples:
{format_examples(examples)}
"""

    return ChatPromptTemplate.from_messages([
        ("system", system_template),
        ("human", "{input}"),
    ])
```

## Agent-Specific Prompts

Example from `src/prompts/biomedical_researcher.md`:

```markdown
# Biomedical Researcher Agent

You are a specialized biomedical research agent with expertise in:
- Literature search across PubMed, BioArxiv, and ClinicalTrials.gov
- Analysis of scientific papers and research findings
- Extraction of relevant biomedical information
- Synthesis of research insights

## Capabilities

1. **Literature Search**: Query biomedical databases for relevant papers
2. **Data Extraction**: Extract key findings, methodologies, and results
3. **Citation Management**: Track sources and maintain references
4. **Synthesis**: Combine findings from multiple sources

## Search Strategy

When conducting literature searches:
1. Identify key terms and MeSH headings
2. Search PubMed for peer-reviewed literature
3. Check BioArxiv for recent preprints
4. Query ClinicalTrials.gov for relevant trials
5. Synthesize findings with proper citations

## Output Format

Always provide:
- Summary of findings
- Source citations (PMID, DOI, or trial ID)
- Confidence level in findings
- Gaps or limitations identified
```

## Loading Agent Prompts

```python
from pathlib import Path

def load_agent_prompt(agent_name: str) -> str:
    """
    Load agent prompt from markdown file.

    Args:
        agent_name: Name of the agent (e.g., 'biomedical_researcher')

    Returns:
        Prompt content as string
    """
    prompt_path = Path(f"src/prompts/{agent_name}.md")
    return prompt_path.read_text()

# Load and use prompt
biomedical_prompt = load_agent_prompt("biomedical_researcher")
```

## Prompt Best Practices

### 1. Clear Role Definition
Start with a clear statement of the agent's role and expertise.

### 2. Explicit Capabilities
List what the agent can and cannot do.

### 3. Output Format
Specify the expected output structure.

### 4. Examples
Include concrete examples when possible.

### 5. Constraints
Define limitations and boundaries clearly.
