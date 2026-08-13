"""Test context window middleware on orchestrator agent."""

from unittest.mock import MagicMock, patch

from langchain.agents.middleware import ContextEditingMiddleware, SummarizationMiddleware


class TestOrchestratorMiddleware:
    """Test that orchestrator is created with context management middleware."""

    def _create_agent_with_mocks(self):
        """Helper to create orchestrator agent with mocked LLM services."""
        with patch("src.agents.orchestrator.LLMService") as mock_llm_service:
            mock_llm_service.get_llm_by_agent.return_value = MagicMock()
            with patch("src.agents.orchestrator.create_agent") as mock_create:
                mock_create.return_value = MagicMock()
                with patch(
                    "src.agents.orchestrator.get_processed_prompt_with_database_context"
                ) as mock_prompt:
                    mock_prompt.return_value = "test prompt"
                    from src.agents.orchestrator import create_orchestrator_agent

                    # Clear the global cache to force creation
                    import src.agents.orchestrator as orch_module

                    orch_module._orchestrator_agents.clear()

                    create_orchestrator_agent()
                    return mock_create

    def test_orchestrator_has_summarization_middleware(self):
        """Verify SummarizationMiddleware is in the middleware list."""
        mock_create = self._create_agent_with_mocks()
        call_kwargs = mock_create.call_args.kwargs
        middleware = call_kwargs.get("middleware", [])
        assert len(middleware) >= 1
        assert any(isinstance(m, SummarizationMiddleware) for m in middleware)

    def test_orchestrator_has_context_editing_middleware(self):
        """Verify ContextEditingMiddleware is in the middleware list."""
        mock_create = self._create_agent_with_mocks()
        call_kwargs = mock_create.call_args.kwargs
        middleware = call_kwargs.get("middleware", [])
        assert any(isinstance(m, ContextEditingMiddleware) for m in middleware)

    def test_middleware_uses_correct_trigger(self):
        """Verify SummarizationMiddleware trigger uses tokens from settings."""
        mock_create = self._create_agent_with_mocks()
        call_kwargs = mock_create.call_args.kwargs
        middleware = call_kwargs.get("middleware", [])

        summarization = next(m for m in middleware if isinstance(m, SummarizationMiddleware))
        # Default: 200_000 * 0.70 = 140_000
        assert summarization.trigger == ("tokens", 140_000)


class TestContextSettings:
    """Test context window settings configuration."""

    def test_default_settings(self):
        """Verify default context window settings."""
        from src.config.settings import settings

        assert settings.context_model_max_tokens == 200_000
        assert settings.context_summary_trigger_fraction == 0.70
        assert settings.context_summary_keep_messages == 20
        assert settings.context_tool_clear_trigger == 140_000
        assert settings.context_tool_clear_keep == 3

    def test_summarizer_agent_config(self):
        """Verify the summarizer resolves to a usable provider and model.

        This previously required a Haiku model, on the grounds that history
        compression runs on every long conversation and should be cheap. That
        constraint was dropped deliberately when the agents moved to Claude 5,
        which has no Haiku tier — the summarizer now shares the same model as
        the workers. Cost is a judgement call rather than an invariant, so only
        resolvability is asserted here.
        """
        from src.config.agents import AGENT_MODEL_SETTINGS, resolve_agent_model

        assert "summarizer" in AGENT_MODEL_SETTINGS
        assert resolve_agent_model("summarizer")
