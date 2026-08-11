"""Research mode configuration for orchestrator behavior.

Defines research modes that control the depth and comprehensiveness of research tasks.
"""

from enum import Enum
from typing import Literal


class ResearchMode(str, Enum):
    """Research mode for orchestrator behavior.

    - STANDARD: Efficient, direct responses. Completes requested tasks without unnecessary exploration.
    - DEEP_RESEARCH: Comprehensive, multi-faceted analysis. Conducts thorough research with iterative deepening,
      cross-validation, and comprehensive synthesis.
    """

    STANDARD = "standard"
    DEEP_RESEARCH = "deep_research"


# Type alias for type hints
ResearchModeType = Literal["standard", "deep_research"]
