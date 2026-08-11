"""Agent backend feature-flag resolver.

Resolves `{agent}_backend` settings fields to an `AgentBackend` enum at runtime.
Phase 0 wired the resolver; Phase 1 adds SDK dispatch in the graph nodes AND
a per-task ContextVar override so the replay harness can safely run concurrent
backend-switching replays without mutating the shared `settings` object (see
``coder_backend_context`` below).
"""

import logging
from contextvars import ContextVar
from enum import Enum

from src.config.settings import settings

logger = logging.getLogger(__name__)


class AgentBackend(str, Enum):
    """Supported agent backends."""

    LANGCHAIN = "langchain"
    SDK = "sdk"


_DEFAULT = AgentBackend.LANGCHAIN

_SETTINGS_FIELD_BY_AGENT: dict[str, str] = {
    "coder": "coder_backend",
    "orchestrator": "orchestrator_backend",
}


# Per-task override for the coder backend. When set (token != None), this
# takes precedence over ``settings.coder_backend`` for THIS asyncio task's
# descendants only. Production code leaves this at its default (None) and
# reads from settings as usual; the evaluation harness uses set/reset in a
# try/finally so concurrent replays each see their own backend.
#
# Why a ContextVar and not a lock: ``asyncio.gather`` and ``create_task``
# propagate ContextVar values into child tasks by default, and each task
# gets its own copy — no coordination needed across concurrent replays.
coder_backend_context: ContextVar[AgentBackend | None] = ContextVar(
    "coder_backend_context", default=None
)

# Per-task override for the ORCHESTRATOR backend. Same semantics as
# ``coder_backend_context`` above. Populated by the Phase 2 evaluation
# harness (Workstream B) and, once the orchestrator prototype graduates
# out of branch-only, by the FastAPI stream_chat handler via a per-request
# ``ChatRequest.orchestrator_backend`` field analogous to coder_backend.
# Until that field lands, this ContextVar is only set by the eval harness
# and tests.
orchestrator_backend_context: ContextVar[AgentBackend | None] = ContextVar(
    "orchestrator_backend_context", default=None
)


def resolve_agent_backend(agent_name: str) -> AgentBackend:
    """Return the backend configured for `agent_name`, defaulting to LANGCHAIN.

    Resolution order for ``"coder"`` and ``"orchestrator"``:
      1. Per-agent ContextVar (``coder_backend_context`` /
         ``orchestrator_backend_context``) — set by the replay harness
         per-call or by ``stream_chat`` per-request. Inherited by child
         asyncio tasks; isolated between concurrent tasks. Takes
         precedence over settings.
      2. ``settings.<agent>_backend`` — the normal production path.
      3. ``AgentBackend.LANGCHAIN`` — default fallback.

    Agents not listed in `_SETTINGS_FIELD_BY_AGENT` (e.g. coordinator, sql_agent,
    summarizer) are always LANGCHAIN — only the three worker-class agents have
    a feature flag. Invalid string values fall back to LANGCHAIN with a warning
    so a typo never hard-fails the request path.
    """
    if agent_name == "coder":
        override = coder_backend_context.get()
        if override is not None:
            return override
    elif agent_name == "orchestrator":
        override = orchestrator_backend_context.get()
        if override is not None:
            return override

    field_name = _SETTINGS_FIELD_BY_AGENT.get(agent_name)
    if field_name is None:
        return _DEFAULT

    raw_value = getattr(settings, field_name, None)
    if raw_value is None:
        return _DEFAULT

    try:
        return AgentBackend(str(raw_value).lower())
    except ValueError:
        logger.warning(
            "Invalid backend value '%s' for agent '%s'; falling back to '%s'",
            raw_value,
            agent_name,
            _DEFAULT.value,
        )
        return _DEFAULT
