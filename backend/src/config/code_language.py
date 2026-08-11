"""Code language configuration for coder agent behavior.

Defines code language options that control which runtime and tools
the coder agent uses for code execution.
"""

from typing import Literal


CodeLanguageType = Literal["python", "r", "auto"]
