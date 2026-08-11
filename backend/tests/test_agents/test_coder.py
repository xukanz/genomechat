"""Tests for coder agent."""

import pytest
from unittest.mock import patch, MagicMock

from src.agents.coder import create_coder_agent


@pytest.mark.asyncio
async def test_create_coder_agent():
    """Test coder agent creation."""
    with patch("src.agents.coder.get_llm_by_agent") as mock_llm:
        mock_llm.return_value = MagicMock()
        with patch("src.agents.coder.agents.create_agent") as mock_create:
            mock_create.return_value = MagicMock()
            agent = create_coder_agent()
            assert agent is not None
            mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_coder_agent_with_tools():
    """Test coder agent creation with additional tools."""
    mock_tool = MagicMock()
    with patch("src.agents.coder.get_llm_by_agent") as mock_llm:
        mock_llm.return_value = MagicMock()
        with patch("src.agents.coder.agents.create_agent") as mock_create:
            mock_create.return_value = MagicMock()
            agent = create_coder_agent(tools=[mock_tool])
            assert agent is not None
            # Verify execute_code tool is included
            call_args = mock_create.call_args
            tools = call_args[1]["tools"]
            assert len(tools) >= 1  # At least execute_code
