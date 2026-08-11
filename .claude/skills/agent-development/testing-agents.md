# Agent Testing Patterns

Testing strategies for multi-agent systems. For core concepts, see [SKILL.md](SKILL.md).

## Contents
- [Unit Testing Agents](#unit-testing-agents)
- [Integration Testing Workflows](#integration-testing-workflows)
- [LLM-as-Judge Evaluation](#llm-as-judge-evaluation)

## Unit Testing Agents

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_research_node_success():
    """Test research node with successful execution."""
    # Arrange
    state = {
        "query": "COVID-19 vaccines",
        "context": {},
        "messages": [],
        "results": [],
        "next_action": "",
        "error": None
    }

    # Mock external calls
    with patch('src.agents.biomedical_researcher.run') as mock_run:
        mock_run.return_value = [
            {"title": "Paper 1", "pmid": "12345"},
            {"title": "Paper 2", "pmid": "67890"}
        ]

        # Act
        result = await research_node(state)

        # Assert
        assert result["error"] is None
        assert len(result["results"]) == 2
        assert result["next_action"] == "analyze"
        mock_run.assert_called_once()

@pytest.mark.asyncio
async def test_research_node_empty_query():
    """Test research node handles empty query."""
    # Arrange
    state = {
        "query": "",
        "context": {},
        "messages": [],
        "results": [],
        "next_action": "",
        "error": None
    }

    # Act
    result = await research_node(state)

    # Assert
    assert result["error"] == "Empty query provided"
    assert result["results"] == []
```

## Integration Testing Workflows

```python
@pytest.mark.asyncio
async def test_complete_research_workflow():
    """Test complete research workflow end-to-end."""
    # Arrange
    initial_state = {
        "query": "TCR analysis methods",
        "messages": [],
        "context": {},
        "results": [],
        "next_action": "",
        "error": None
    }

    # Act
    workflow = create_research_workflow()
    app = workflow.compile()
    result = await app.ainvoke(initial_state)

    # Assert
    assert result["error"] is None
    assert len(result["results"]) > 0
    assert "messages" in result
    assert len(result["messages"]) > 0
```

## LLM-as-Judge Evaluation

Located in `evals/agents/`:

```python
from langchain.evaluation import load_evaluator

def evaluate_research_quality(query: str, results: list[dict]) -> dict:
    """
    Evaluate research results using LLM-as-judge.

    Args:
        query: Original research query
        results: Research results to evaluate

    Returns:
        Evaluation metrics including relevance, completeness, accuracy
    """
    evaluator = load_evaluator("criteria", criteria="relevance")

    # Format results for evaluation
    results_text = format_results(results)

    # Run evaluation
    eval_result = evaluator.evaluate_strings(
        prediction=results_text,
        input=query,
        criteria={
            "relevance": "Results are relevant to the query",
            "completeness": "Results comprehensively address the query",
            "accuracy": "Results are scientifically accurate"
        }
    )

    return eval_result
```

## Testing Best Practices

### Mock External Dependencies

```python
@pytest.fixture
def mock_llm():
    """Mock LLM for testing without API calls."""
    with patch('langchain_openai.ChatOpenAI') as mock:
        mock.return_value.ainvoke.return_value = AIMessage(content="Test response")
        yield mock
```

### Test Error Paths

```python
@pytest.mark.asyncio
async def test_node_handles_api_error():
    """Test node gracefully handles API errors."""
    with patch('src.agents.agent.run', side_effect=APIError("Rate limited")):
        result = await agent_node(state)
        assert result["error"] is not None
        assert result["next_action"] == "retry"
```

### Use Fixtures for State

```python
@pytest.fixture
def initial_state():
    """Standard initial state for workflow tests."""
    return {
        "query": "Test query",
        "messages": [],
        "context": {},
        "results": [],
        "next_action": "",
        "error": None
    }
```
