"""SQL agent configuration settings.

Defines configuration for switching between graph-based and agentic SQL agent systems.
"""

from enum import Enum
from typing import Literal

from pydantic_settings import BaseSettings


class SQLAgentMode(str, Enum):
    """SQL agent system modes."""

    GRAPH = "graph"
    AGENTIC = "agentic"


class SQLAgentConfig(BaseSettings):
    """SQL agent configuration settings."""

    sql_agent_mode: Literal["graph", "agentic"] = SQLAgentMode.AGENTIC

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Global config instance
sql_agent_config = SQLAgentConfig()
