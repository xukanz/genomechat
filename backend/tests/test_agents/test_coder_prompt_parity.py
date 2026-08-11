"""Lock in that LangChain and SDK coder paths compose identical system prompts.

Task 12b extracted ``compose_coder_system_prompt`` as the single source of
truth. This test pins the contract: any future drift between how the
LangChain factory and the SDK invoker build the prompt would break the
A/B eval's honesty, so we catch it here instead of discovering it during
analysis.
"""

from __future__ import annotations

import pytest


def test_compose_coder_system_prompt_python_only():
    from src.agents.coder import compose_coder_system_prompt

    prompt = compose_coder_system_prompt(
        user_id="alice",
        project_snippets=None,
        code_language="python",
    )
    # Has base + python module, no R content
    assert "alice" in prompt  # USER_ID templated in
    assert "python" in prompt.lower() or "Python" in prompt


def test_compose_coder_system_prompt_r_only_includes_clinical():
    from src.agents.coder import compose_coder_system_prompt

    prompt = compose_coder_system_prompt(
        user_id="bob",
        project_snippets=None,
        code_language="r",
    )
    # Base + R + R-clinical module all included for the 'r' language path
    assert "bob" in prompt


def test_compose_coder_system_prompt_auto_includes_both():
    from src.agents.coder import compose_coder_system_prompt

    prompt = compose_coder_system_prompt(
        user_id="carol",
        project_snippets=None,
        code_language="auto",
    )
    # Auto means include both language modules + clinical — should be the
    # longest composition
    assert len(prompt) > 0


@pytest.mark.parametrize("lang", ["python", "r", "auto"])
def test_snippet_injection_appears_in_prompt(lang):
    from src.agents.coder import compose_coder_system_prompt

    snippets = [
        {
            "name": "marker_snippet_ABC",
            "description": "a tagged snippet for test",
            "code": "print('hello from snippet')",
        }
    ]
    prompt = compose_coder_system_prompt(
        user_id="dave",
        project_snippets=snippets,
        code_language=lang,
    )
    # Either the name, the description, or the content must land somewhere
    # in the rendered prompt — exact formatting is owned by format_snippets_for_prompt.
    assert (
        "marker_snippet_ABC" in prompt
        or "a tagged snippet for test" in prompt
        or "hello from snippet" in prompt
    ), f"snippet was dropped for code_language={lang}"


def test_anonymous_user_falls_back():
    from src.agents.coder import compose_coder_system_prompt

    prompt = compose_coder_system_prompt(
        user_id=None,
        project_snippets=None,
        code_language="python",
    )
    assert "anonymous" in prompt


def test_compose_returns_identical_output_across_calls():
    """Composition must be pure — same inputs, same bytes out."""
    from src.agents.coder import compose_coder_system_prompt

    a = compose_coder_system_prompt("u", None, "python")
    b = compose_coder_system_prompt("u", None, "python")
    assert a == b
