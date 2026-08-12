"""Regression test — the coordinator's direct answer must be an AIMessage.

Backstory: ``coordinator_node`` used to persist its user-facing answer as
``HumanMessage(content=..., name="coordinator")``. LangChain maps
``HumanMessage`` to ``role: user``, so every coordinator reply was written
into graph state as if the *user* had said it.

After one direct answer the checkpointed history contained no assistant
turn at all — user question, coordinator reply, user question, coordinator
reply, all of them ``role: user``. The coordinator could no longer tell the
new question apart from its own previous reply, and on the next turn it
re-answered the PREVIOUS question, offering the actual new one back as a
numbered "suggestion".

Observed against a real thread: a user asked for a Manhattan plot, was
correctly told ClinVar has no GWAS data, then asked for a ClinVar bar chart
and got the Manhattan refusal again — twice.

These tests pin the role, not just the type name, because the role is what
actually reaches the provider.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.graph.types import CoordinatorResponse


def _run_coordinator(messages: list[BaseMessage], decision: CoordinatorResponse):
    """Invoke coordinator_node with the LLM and prompt loader mocked out."""
    with (
        patch("src.graph.nodes.LLMService") as mock_llm_service,
        patch("src.graph.nodes.get_processed_prompt_with_database_context") as mock_prompt,
    ):
        mock_prompt.return_value = "test coordinator prompt"

        structured = MagicMock()
        structured.invoke.return_value = decision
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        mock_llm_service.get_llm_by_agent.return_value = llm
        mock_llm_service.get_structured_output_method_for_agent.return_value = "function_calling"

        from src.graph.nodes import coordinator_node

        return coordinator_node({"messages": messages})


def _added(command) -> list[BaseMessage]:
    return (command.update or {}).get("messages", [])


class TestCoordinatorDirectResponse:
    def test_direct_answer_is_an_ai_message(self):
        command = _run_coordinator(
            [HumanMessage(content="hello")],
            CoordinatorResponse(action="respond", response="Hi there!", reasoning="small talk"),
        )

        answers = [m for m in _added(command) if getattr(m, "name", None) == "coordinator"]
        assert len(answers) == 1, f"expected exactly one coordinator answer, got {answers!r}"
        assert isinstance(answers[0], AIMessage)
        assert answers[0].type == "ai", (
            "the coordinator's answer must reach the provider as role: assistant — "
            "persisting it as role: user is what made the coordinator mistake its "
            "own past replies for user questions"
        )
        assert answers[0].content == "Hi there!"

    def test_direct_answer_is_never_a_human_turn(self):
        command = _run_coordinator(
            [HumanMessage(content="hello")],
            CoordinatorResponse(action="respond", response="Hi there!", reasoning="small talk"),
        )

        offenders = [
            m
            for m in _added(command)
            if isinstance(m, HumanMessage) and getattr(m, "name", None) == "coordinator"
        ]
        assert not offenders, (
            f"coordinator emitted its answer as a HumanMessage: {offenders!r}. "
            f"That maps to role: user and poisons the next turn's history."
        )

    def test_routing_turn_does_not_emit_an_answer(self):
        """Handing off must not inject a fake assistant answer — the orchestrator answers."""
        command = _run_coordinator(
            [HumanMessage(content="count variants by significance")],
            CoordinatorResponse(
                action="handoff_to_orchestrator",
                response="",
                reasoning="needs a database query",
            ),
        )

        assert command.goto == "orchestrator"
        assert not [m for m in _added(command) if getattr(m, "name", None) == "coordinator"]


class TestMultiTurnRoleSequence:
    """The failure only showed up on the SECOND question, so simulate two turns."""

    def test_latest_user_turn_is_the_new_question(self):
        history: list[BaseMessage] = []

        history.append(HumanMessage(content="Draw a Manhattan plot of GWAS associations."))
        history += _added(
            _run_coordinator(
                history,
                CoordinatorResponse(
                    action="respond",
                    response="ClinVar has no GWAS summary statistics.",
                    reasoning="wrong database for the request",
                ),
            )
        )

        new_question = "Make a bar chart of ClinVar variant counts by clinical significance."
        history.append(HumanMessage(content=new_question))

        user_turns = [m for m in history if m.type == "human"]
        assert user_turns[-1].content == new_question, (
            "the newest user turn must be the user's actual question; if a coordinator "
            "reply lands here the model answers the previous question instead"
        )

        assert any(m.type == "ai" for m in history), (
            "history must contain at least one assistant turn after the coordinator "
            "answers — an all-user history is exactly the bug this pins"
        )
