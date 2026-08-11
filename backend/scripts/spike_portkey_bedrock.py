"""Phase 0 pre-phase spike — Portkey Bedrock connectivity + token metadata check.

Covers three spike goals:

1. **LangChain path via Portkey Bedrock** — confirm `LLMService.get_llm_by_agent("summarizer")`
   invokes successfully and the response carries token usage we can cost-attribute.

2. **Structured output (JSON mode) via Portkey Bedrock** — confirm Haiku supports
   `with_structured_output(method="json_mode")` through the gateway. This is a
   precondition for several Phase 0+ paths (memory extractor, LLM judge, etc.).

3. **Claude Agent SDK path** — confirm we can route SDK queries through Portkey
   when we flip `CODER_BACKEND=sdk` in Phase 1. This spike validates the
   theoretical path; a failure here is NOT a Phase 0 blocker (Phase 0 is
   LangChain-only) but it DOES need to be resolved before Phase 1.

Usage:
    cd backend && uv run python scripts/spike_portkey_bedrock.py

Writes a structured findings block to stdout; redirect to a file if you want
to capture it for the spike findings doc.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Spike helpers
# ---------------------------------------------------------------------------


def _section(title: str) -> None:
    """Print a section divider."""
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _result(status: str, msg: str) -> None:
    """Print a single result line with a PASS/FAIL/INFO prefix."""
    marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "INFO": "[INFO]", "SKIP": "[SKIP]"}[status]
    print(f"  {marker} {msg}")


def _dump(label: str, obj: Any, max_chars: int = 800) -> None:
    """Print a labeled object, truncating long strings."""
    if isinstance(obj, dict | list):
        rendered = json.dumps(obj, default=str, indent=2)
    else:
        rendered = str(obj)
    if len(rendered) > max_chars:
        rendered = rendered[:max_chars] + f"\n    ... [truncated {len(rendered) - max_chars} chars]"
    print(f"  {label}:")
    for line in rendered.splitlines():
        print(f"    {line}")


# ---------------------------------------------------------------------------
# Test 1 — LangChain + Portkey Bedrock (sanity + token metadata)
# ---------------------------------------------------------------------------


def test_langchain_portkey_bedrock() -> dict[str, Any]:
    """Invoke Haiku through the existing LLMService and capture token metadata."""
    _section("Test 1 — LangChain via Portkey Bedrock (summarizer slot = Haiku)")

    try:
        from src.service.llm import LLMService
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"import LLMService failed: {e}")
        return {"status": "fail", "reason": "import"}

    try:
        llm = LLMService.get_llm_by_agent("summarizer", streaming=False, temperature=0.0)
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"get_llm_by_agent('summarizer') failed: {e}")
        return {"status": "fail", "reason": "factory"}

    t0 = time.perf_counter()
    try:
        resp = llm.invoke("Respond with exactly one word: pong")
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"llm.invoke raised: {e}")
        return {"status": "fail", "reason": "invoke"}
    elapsed_ms = (time.perf_counter() - t0) * 1000

    _result("PASS", f"invoke succeeded in {elapsed_ms:.0f}ms")
    _dump("content", resp.content)
    _dump("response_metadata", resp.response_metadata)
    _dump("usage_metadata", getattr(resp, "usage_metadata", None))

    # Identify which shape the token counts land in — this decides cost.py's design
    usage_source = None
    input_tokens = output_tokens = None

    usage_meta = getattr(resp, "usage_metadata", None) or {}
    if usage_meta.get("input_tokens") is not None:
        usage_source = "usage_metadata"
        input_tokens = usage_meta.get("input_tokens")
        output_tokens = usage_meta.get("output_tokens")

    rm = resp.response_metadata or {}
    for candidate in ("token_usage", "usage"):
        if candidate in rm and input_tokens is None:
            usage_source = f"response_metadata.{candidate}"
            usage_obj = rm[candidate]
            # Support both OpenAI-style (prompt_tokens/completion_tokens) and Anthropic (input/output)
            input_tokens = (
                usage_obj.get("prompt_tokens")
                or usage_obj.get("input_tokens")
                or usage_obj.get("inputTokens")
            )
            output_tokens = (
                usage_obj.get("completion_tokens")
                or usage_obj.get("output_tokens")
                or usage_obj.get("outputTokens")
            )

    if input_tokens is not None and output_tokens is not None:
        _result(
            "PASS",
            f"token usage captured via {usage_source}: "
            f"input={input_tokens}, output={output_tokens}",
        )
    else:
        _result(
            "FAIL",
            "could not extract token usage — cost.py must be redesigned to match this response shape",
        )

    return {
        "status": "pass" if input_tokens and output_tokens else "fail",
        "usage_source": usage_source,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": elapsed_ms,
        "response_metadata_keys": list((resp.response_metadata or {}).keys()),
    }


# ---------------------------------------------------------------------------
# Test 2 — Structured output (JSON mode) via Portkey Bedrock
# ---------------------------------------------------------------------------


class _Ping(BaseModel):
    """Structured-output smoke test payload."""

    response: str = Field(description="Must be the single word 'pong'")
    confidence: float = Field(ge=0.0, le=1.0)


def test_structured_output() -> dict[str, Any]:
    """Confirm Haiku + Portkey Bedrock + JSON mode returns a valid Pydantic instance."""
    _section("Test 2 — Structured output (JSON mode) via Portkey Bedrock")

    try:
        from src.service.llm import LLMService
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"import LLMService failed: {e}")
        return {"status": "fail", "reason": "import"}

    try:
        method = LLMService.get_structured_output_method_for_agent("summarizer")
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"get_structured_output_method_for_agent failed: {e}")
        return {"status": "fail", "reason": "method-lookup"}

    _result("INFO", f"structured output method for summarizer: {method}")

    try:
        llm = LLMService.get_llm_by_agent("summarizer", streaming=False, temperature=0.0)
        structured = llm.with_structured_output(_Ping, method=method)
        result = structured.invoke("Return response='pong' and confidence=0.95")
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"structured-output invoke failed: {e}")
        return {"status": "fail", "reason": "structured-invoke", "error": str(e)}

    _dump("parsed result", result.model_dump())

    ok = isinstance(result, _Ping) and bool(result.response)
    _result("PASS" if ok else "FAIL", "Pydantic parsing succeeded" if ok else "parsing mismatch")
    return {"status": "pass" if ok else "fail", "method": method, "parsed": result.model_dump()}


# ---------------------------------------------------------------------------
# Test 3 — Claude Agent SDK via Portkey Bedrock (forward-compat for Phase 1)
# ---------------------------------------------------------------------------


async def test_sdk_via_portkey() -> dict[str, Any]:
    """Attempt a minimum SDK `query()` routed through Portkey.

    We try two scenarios in priority order:
      A. ANTHROPIC_BASE_URL + ANTHROPIC_CUSTOM_HEADERS (Anthropic-compat virtual key)
      B. CLAUDE_CODE_USE_BEDROCK + ANTHROPIC_BEDROCK_BASE_URL (native Bedrock via Portkey)

    A failure here is NOT a Phase 0 blocker — Phase 0 is LangChain-only. But we
    document which path works so Phase 1 knows how to configure the SDK.
    """
    _section("Test 3 — Claude Agent SDK via Portkey (forward-compat for Phase 1)")

    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"import claude_agent_sdk failed: {e}")
        return {"status": "fail", "reason": "import"}

    try:
        from src.config.settings import settings
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"import settings failed: {e}")
        return {"status": "fail", "reason": "settings-import"}

    if not settings.portkey_bedrock_api_key or not settings.portkey_bedrock_slug:
        _result("SKIP", "Portkey Bedrock credentials not configured — skipping SDK path")
        return {"status": "skip", "reason": "no-creds"}

    # Portkey slug only — the API key authenticates via ANTHROPIC_AUTH_TOKEN
    # (which the bundled Anthropic SDK sends as `Authorization: Bearer`, which
    # Portkey accepts). Using ANTHROPIC_API_KEY instead produces `x-api-key`,
    # which Portkey rejects with "Invalid API Key. Error Code: 03".
    portkey_headers = f"x-portkey-slug: {settings.portkey_bedrock_slug}"

    # Scenario A: Anthropic-compat virtual key via ANTHROPIC_BASE_URL
    # Auth via ANTHROPIC_AUTH_TOKEN → `Authorization: Bearer <portkey_key>`
    # Slug via ANTHROPIC_CUSTOM_HEADERS → `x-portkey-slug: <slug>`
    #
    # Use portkey_anthropic_base_url (strips trailing /v1) — the bundled CLI
    # appends /v1/messages itself. Passing the /v1-suffixed form produces
    # /v1/v1/messages, which Portkey forwards to Bedrock and Bedrock rejects
    # as an AWS Coral UnknownOperationException (HTTP 200, unparseable body).
    # This discrepancy was only observed in the Podman container path during
    # Phase 1 container validation on 2026-05-08 — the macOS host happened
    # to tolerate it, which masked the bug until then.
    scenario_a_env = {
        "ANTHROPIC_BASE_URL": settings.portkey_anthropic_base_url,
        "ANTHROPIC_AUTH_TOKEN": settings.portkey_bedrock_api_key,
        "ANTHROPIC_CUSTOM_HEADERS": portkey_headers,
        # Explicitly unset ANTHROPIC_API_KEY if the parent process has one;
        # presence of it forces `x-api-key` auth which Portkey rejects.
        # The SDK `env` dict is an overlay over the parent env, so we
        # overwrite with an empty string here — the bundled CLI treats empty
        # as unset when deciding which auth path to use.
        "ANTHROPIC_API_KEY": "",
    }

    _result("INFO", "Scenario A: ANTHROPIC_BASE_URL + ANTHROPIC_CUSTOM_HEADERS")
    _dump(
        "env override (A)",
        {k: (v if "KEY" not in k.upper() else "<redacted>") for k, v in scenario_a_env.items()},
    )

    options_a = ClaudeAgentOptions(
        # Use the Bedrock-flavored model ID that Portkey expects —
        # "claude-haiku-4-5" (Anthropic-native alias) returns 400 through Portkey
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        env=scenario_a_env,
        # Minimum options: remove built-in tools so the call only exercises LLM routing
        tools=[],
        allowed_tools=[],
        max_turns=1,
        permission_mode="bypassPermissions",
    )

    scenario_a_result: dict[str, Any] = {"scenario": "A", "status": "unknown"}
    try:
        t0 = time.perf_counter()
        collected: list[str] = []
        async for msg in query(prompt="Respond with exactly one word: pong", options=options_a):
            # Collect any text content we see
            name = type(msg).__name__
            collected.append(name)
            if hasattr(msg, "result"):
                scenario_a_result["final_result_preview"] = str(getattr(msg, "result"))[:200]
            if hasattr(msg, "content"):
                for block in getattr(msg, "content", []) or []:
                    if hasattr(block, "text"):
                        scenario_a_result.setdefault("text_blocks", []).append(block.text[:200])
        elapsed_ms = (time.perf_counter() - t0) * 1000
        scenario_a_result["status"] = "pass"
        scenario_a_result["message_types"] = collected
        scenario_a_result["latency_ms"] = elapsed_ms
        _result("PASS", f"Scenario A succeeded in {elapsed_ms:.0f}ms, messages: {collected}")
    except Exception as e:  # noqa: BLE001
        scenario_a_result["status"] = "fail"
        scenario_a_result["error"] = f"{type(e).__name__}: {e}"
        _result("FAIL", f"Scenario A failed: {type(e).__name__}: {e}")

    # If Scenario A worked, we're done
    if scenario_a_result["status"] == "pass":
        return {"status": "pass", "winning_scenario": "A", "scenario_a": scenario_a_result}

    # Scenario B: native Bedrock mode pointed at Portkey's Bedrock endpoint
    # (less preferred than A — CLAUDE_CODE_USE_BEDROCK triggers AWS SigV4 signing
    # which Portkey does NOT accept; kept here for completeness)
    _result("INFO", "Scenario B: CLAUDE_CODE_USE_BEDROCK + ANTHROPIC_BEDROCK_BASE_URL")
    scenario_b_env = {
        "CLAUDE_CODE_USE_BEDROCK": "1",
        # Same /v1-stripping rationale as Scenario A.
        "ANTHROPIC_BEDROCK_BASE_URL": settings.portkey_anthropic_base_url,
        "ANTHROPIC_AUTH_TOKEN": settings.portkey_bedrock_api_key,
        "ANTHROPIC_CUSTOM_HEADERS": portkey_headers,
        "AWS_REGION": settings.aws_default_region,
        "ANTHROPIC_API_KEY": "",
    }
    _dump(
        "env override (B)",
        {k: (v if "KEY" not in k.upper() else "<redacted>") for k, v in scenario_b_env.items()},
    )

    options_b = ClaudeAgentOptions(
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        env=scenario_b_env,
        tools=[],
        allowed_tools=[],
        max_turns=1,
        permission_mode="bypassPermissions",
    )

    scenario_b_result: dict[str, Any] = {"scenario": "B", "status": "unknown"}
    try:
        t0 = time.perf_counter()
        collected_b: list[str] = []
        async for msg in query(prompt="Respond with exactly one word: pong", options=options_b):
            name = type(msg).__name__
            collected_b.append(name)
            if hasattr(msg, "result"):
                scenario_b_result["final_result_preview"] = str(getattr(msg, "result"))[:200]
            if hasattr(msg, "content"):
                for block in getattr(msg, "content", []) or []:
                    if hasattr(block, "text"):
                        scenario_b_result.setdefault("text_blocks", []).append(block.text[:200])
        elapsed_ms = (time.perf_counter() - t0) * 1000
        scenario_b_result["status"] = "pass"
        scenario_b_result["message_types"] = collected_b
        scenario_b_result["latency_ms"] = elapsed_ms
        _result("PASS", f"Scenario B succeeded in {elapsed_ms:.0f}ms, messages: {collected_b}")
    except Exception as e:  # noqa: BLE001
        scenario_b_result["status"] = "fail"
        scenario_b_result["error"] = f"{type(e).__name__}: {e}"
        _result("FAIL", f"Scenario B failed: {type(e).__name__}: {e}")

    winning = (
        "A"
        if scenario_a_result["status"] == "pass"
        else ("B" if scenario_b_result["status"] == "pass" else None)
    )
    return {
        "status": "pass" if winning else "fail",
        "winning_scenario": winning,
        "scenario_a": scenario_a_result,
        "scenario_b": scenario_b_result,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _main() -> int:
    # Ensure backend/src is importable when invoked from the backend/ directory
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print("Phase 0 pre-phase spike — Portkey Bedrock connectivity check")
    print(f"  python={sys.version.split()[0]}")

    # Sanity-check that SDK imported
    try:
        import claude_agent_sdk  # noqa: F401

        sdk_version = getattr(
            __import__("importlib.metadata", fromlist=["version"]),
            "version",
        )("claude-agent-sdk")
        print(f"  claude-agent-sdk={sdk_version}")
    except Exception as e:  # noqa: BLE001
        print(f"  claude-agent-sdk import failed: {e}")

    results: dict[str, Any] = {}

    results["langchain_portkey"] = test_langchain_portkey_bedrock()
    results["structured_output"] = test_structured_output()
    results["sdk_via_portkey"] = await test_sdk_via_portkey()

    _section("Summary")
    for name, result in results.items():
        status = result.get("status", "unknown")
        marker = {"pass": "[PASS]", "fail": "[FAIL]", "skip": "[SKIP]"}.get(status, "[????]")
        print(f"  {marker} {name}: {status}")

    print("\nFull results (machine-readable):")
    print(json.dumps(results, default=str, indent=2))

    # Exit code: non-zero if the LangChain path failed (hard Phase 0 blocker).
    # SDK path failures are soft warnings (Phase 1 concern only).
    return 0 if results["langchain_portkey"]["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
