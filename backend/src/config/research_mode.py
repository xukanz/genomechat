"""Research mode configuration for orchestrator behavior.

Defines research modes that control the depth and comprehensiveness of research tasks.

- standard: Efficient, direct responses. Completes requested tasks without unnecessary
  exploration.
- deep_research: Comprehensive, multi-faceted analysis. Conducts thorough research with
  iterative deepening, cross-validation, and comprehensive synthesis.
"""

from typing import Literal

ResearchModeType = Literal["standard", "deep_research"]
