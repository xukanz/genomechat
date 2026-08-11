"""Phase 1 SDK runtime helpers — transcript isolation and cleanup.

Two observations from the Phase 1 Spike 2 findings shape this module:

1. ``cwd`` isolation works. Passing ``ClaudeAgentOptions(cwd=<unique-dir>)`` per
   ``query()`` call gives collision-free transcripts across concurrent requests.

2. **The SDK does not write transcripts into ``cwd``.** It writes to
   ``~/.claude/projects/<project_key>/<session_id>.jsonl`` where
   ``project_key = _sanitize_path(realpath(cwd))``. The ``cwd`` directory we
   create is purely a namespace anchor; the actual transcript bytes live under
   the SDK's projects dir. Cleanup logic MUST target the projects dir or the
   home volume grows without bound.

We import ``project_key_for_directory`` and ``_get_projects_dir`` directly from
``claude_agent_sdk._internal.sessions``. These are technically private but are
the SDK's own canonical implementations — re-deriving the sanitization would
be a silent drift risk on any future SDK revision. The module-level import
probe in ``_load_sdk_session_utils()`` lets us fall back to a best-effort
reimplementation if the SDK ever moves these functions.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Callable

from src.config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SDK internal interop — resolve the encoding the SDK actually uses.
# ---------------------------------------------------------------------------


def _fallback_sanitize_path(name: str) -> str:
    """Best-effort fallback matching the SDK's ``_sanitize_path``.

    Used only if the SDK private import fails. Observed algorithm from the
    Phase 1 spike: non-alphanumeric → ``-``, no length cap applied (the
    200-char truncation with hash suffix is unused for our short paths).
    """
    return re.sub(r"[^a-zA-Z0-9]", "-", name)


def _fallback_canonicalize_path(d: str) -> str:
    try:
        return unicodedata.normalize("NFC", os.path.realpath(d))
    except OSError:
        return unicodedata.normalize("NFC", d)


def _load_sdk_session_utils() -> tuple[Callable[[str | Path | None], str], Callable[[], Path]]:
    """Return ``(project_key_for_directory, get_projects_dir)`` from the SDK.

    Falls back to local reimplementations if the SDK's private internals move.
    The fallback loses the djb2-hash truncation behavior for paths > 200 chars;
    we never produce such paths (transcript_root + instance_id + uuid is
    well under 100), so the fallback is equivalent in practice.
    """
    try:
        from claude_agent_sdk._internal.sessions import (  # type: ignore[import-untyped]
            _get_projects_dir as sdk_get_projects_dir,
            project_key_for_directory as sdk_project_key,
        )

        return sdk_project_key, sdk_get_projects_dir  # type: ignore[return-value]
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "claude_agent_sdk._internal.sessions unavailable (%s); "
            "using fallback transcript-path encoder",
            e,
        )

        def _fallback_project_key(directory: str | Path | None = None) -> str:
            abs_path = _fallback_canonicalize_path(str(directory) if directory is not None else ".")
            return _fallback_sanitize_path(abs_path)

        def _fallback_projects_dir() -> Path:
            override = os.environ.get("CLAUDE_CONFIG_DIR")
            if override:
                return Path(unicodedata.normalize("NFC", override)) / "projects"
            return Path(unicodedata.normalize("NFC", str(Path.home() / ".claude"))) / "projects"

        return _fallback_project_key, _fallback_projects_dir


_project_key_for_directory, _get_projects_dir = _load_sdk_session_utils()


# ---------------------------------------------------------------------------
# Instance ID resolution — uniform across Podman / Docker / K8s / bare-metal
# ---------------------------------------------------------------------------


def resolve_instance_id() -> str:
    """Stable per-container identifier.

    Precedence:
      1. ``INSTANCE_ID`` explicit override
      2. K8s downward API: ``POD_NAME``
      3. Container runtime default: ``HOSTNAME``
      4. Bare-metal / local dev: ``local-<uuid4>`` fallback
    """
    for var in ("INSTANCE_ID", "POD_NAME", "HOSTNAME"):
        val = os.environ.get(var)
        if val:
            return val
    return f"local-{uuid.uuid4().hex[:8]}"


_INSTANCE_ID: str = resolve_instance_id()


def instance_id() -> str:
    """Return this process's resolved INSTANCE_ID (cached at import time)."""
    return _INSTANCE_ID


# ---------------------------------------------------------------------------
# Per-request transcript anchor dirs
# ---------------------------------------------------------------------------


def build_transcript_dir(thread_id: str, request_id: str | None = None) -> Path:
    """Return a unique per-request anchor directory.

    Layout: ``${SDK_TRANSCRIPT_ROOT}/${INSTANCE_ID}/${thread_id}/${request_id}/``

    The SDK will not write transcript bytes here — see module docstring. This
    directory exists purely so that its absolute path, when sanitized by the
    SDK, yields a unique ``~/.claude/projects/<project_key>/`` subdirectory
    for the request.
    """
    req_id = request_id or uuid.uuid4().hex
    thread_component = thread_id or "_no_thread"
    root = Path(settings.sdk_transcript_root) / _INSTANCE_ID / thread_component / req_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def transcript_projects_dir_for(cwd: str | Path) -> Path:
    """Return the ``~/.claude/projects/<project_key>/`` dir the SDK will write to.

    Use to clean up after a ``query()`` call completes, or to audit what the
    SDK wrote during a run.
    """
    project_key = _project_key_for_directory(str(cwd))
    return _get_projects_dir() / project_key


def cleanup_request_artifacts(cwd: str | Path) -> None:
    """Remove both the anchor dir and the SDK's projects dir for one request.

    Intended to be called from ``coder_sdk.py``'s ``finally`` block. Failures
    on either leg are logged and swallowed — we never let cleanup raise out
    of the request path.
    """
    cwd_path = Path(cwd)
    projects_dir = transcript_projects_dir_for(cwd_path)

    for target in (projects_dir, cwd_path):
        try:
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
        except Exception:  # noqa: BLE001
            logger.exception("cleanup_request_artifacts: failed to sweep %s", target)


# ---------------------------------------------------------------------------
# Periodic orphan sweep — crashed-request recovery
# ---------------------------------------------------------------------------


def _instance_anchor_root() -> Path:
    """Return ``${SDK_TRANSCRIPT_ROOT}/${INSTANCE_ID}``."""
    return Path(settings.sdk_transcript_root) / _INSTANCE_ID


def _encoded_instance_prefix() -> str:
    """Encoded-prefix that every request's ``project_key`` for this instance starts with.

    Matches what the SDK produces for any ``cwd`` that lives under this
    instance's anchor root. Used to filter ``~/.claude/projects/`` entries
    to this instance only — critical when multiple containers share a home
    volume or run on the same host.
    """
    return _project_key_for_directory(str(_instance_anchor_root()))


def cleanup_orphans(max_age_seconds: int | None = None) -> int:
    """Sweep stale transcript artifacts belonging to this instance.

    Two targets:
      1. ``~/.claude/projects/<project_key>/`` entries whose ``project_key``
         starts with this instance's encoded anchor prefix
      2. Empty anchor dirs under ``${SDK_TRANSCRIPT_ROOT}/${INSTANCE_ID}/``

    Only entries whose most-recent-modification time is older than
    ``max_age_seconds`` are removed. Returns the count of removed entries
    across both targets.

    This is idempotent and safe to run concurrently with active requests —
    the per-request anchor is owned by the request task and its mtime is
    refreshed on SDK writes, so it won't be old enough to sweep while in use.
    """
    max_age = (
        max_age_seconds
        if max_age_seconds is not None
        else settings.sdk_orphan_cleanup_max_age_seconds
    )
    cutoff = time.time() - max_age
    removed = 0

    # 1. Sweep ~/.claude/projects/<project_key>/ for this instance
    projects_dir = _get_projects_dir()
    prefix = _encoded_instance_prefix()
    if projects_dir.exists():
        try:
            for entry in projects_dir.iterdir():
                if not entry.is_dir() or not entry.name.startswith(prefix):
                    continue
                try:
                    if entry.stat().st_mtime < cutoff:
                        shutil.rmtree(entry, ignore_errors=True)
                        removed += 1
                except Exception:  # noqa: BLE001
                    logger.exception("cleanup_orphans: failed to sweep %s", entry)
        except Exception:  # noqa: BLE001
            logger.exception("cleanup_orphans: failed to iterate %s", projects_dir)

    # 2. Sweep ${SDK_TRANSCRIPT_ROOT}/${INSTANCE_ID}/<thread_id>/<request_id>/
    anchor_root = _instance_anchor_root()
    if anchor_root.exists():
        try:
            for thread_dir in anchor_root.iterdir():
                if not thread_dir.is_dir():
                    continue
                for req_dir in thread_dir.iterdir():
                    if not req_dir.is_dir():
                        continue
                    try:
                        if req_dir.stat().st_mtime < cutoff:
                            shutil.rmtree(req_dir, ignore_errors=True)
                            removed += 1
                    except Exception:  # noqa: BLE001
                        logger.exception("cleanup_orphans: failed to sweep %s", req_dir)
        except Exception:  # noqa: BLE001
            logger.exception("cleanup_orphans: failed to iterate %s", anchor_root)

    if removed:
        logger.info("cleanup_orphans: swept %d orphaned transcript artifact(s)", removed)
    return removed


__all__ = [
    "build_transcript_dir",
    "cleanup_orphans",
    "cleanup_request_artifacts",
    "instance_id",
    "resolve_instance_id",
    "transcript_projects_dir_for",
]
