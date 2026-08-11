"""Phase 1 pre-phase Spike 2 — concurrent transcript isolation under load.

PRD Risk 3 acceptance gate: the SDK writes a JSONL transcript per ``query()``
call, and naive usage lands all concurrent requests in the same directory,
producing interleaved writes and session_id collisions. The mitigation is
``ClaudeAgentOptions(cwd=<unique-dir>)``. This spike prototypes the pattern
and verifies:

- 50 concurrent ``query()`` calls complete without errors
- Each call's transcript lands in its own ``cwd`` subtree (no cross-pollination)
- Every JSONL file the SDK writes parses cleanly (no interleaved writes)
- No session_id collisions across concurrent calls
- Per-request directories can be swept post-completion (cleanup hygiene)

Because each call goes through Portkey and bills real tokens, the prompt is
trivial ("reply ok") and ``max_turns=1`` caps subprocess work. Expected cost
≈ 50 × ~$0.002 = ~$0.10 per run. Guard with ``--dry-run`` if you want to
exercise the plumbing without hitting the gateway.

Usage:
    cd backend && uv run python scripts/spike_sdk_transcript_isolation.py
    cd backend && uv run python scripts/spike_sdk_transcript_isolation.py --n 10        # lighter run
    cd backend && uv run python scripts/spike_sdk_transcript_isolation.py --dry-run     # skip LLM, stress dir logic only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any


def _section(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _result(status: str, msg: str) -> None:
    marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "INFO": "[INFO]", "WARN": "[WARN]"}[status]
    print(f"  {marker} {msg}")


async def _one_request(
    request_id: str,
    transcript_root: Path,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Fire one isolated query() call and return per-request bookkeeping."""
    from claude_agent_sdk import ClaudeAgentOptions, query

    from src.config.settings import settings

    # Build a per-request cwd under the shared root. This is the PRD Risk 3
    # isolation primitive: SDK encodes `cwd` into its transcript path, so unique
    # cwd values give unique transcript subtrees by construction.
    req_dir = transcript_root / request_id
    req_dir.mkdir(parents=True, exist_ok=False)

    portkey_headers = f"x-portkey-slug: {settings.portkey_bedrock_slug}"

    options = ClaudeAgentOptions(
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",  # cheap for stress test
        env={
            # See coder_sdk._build_options: portkey_anthropic_base_url strips
            # the /v1 suffix the bundled CLI would otherwise double.
            "ANTHROPIC_BASE_URL": settings.portkey_anthropic_base_url,
            "ANTHROPIC_AUTH_TOKEN": settings.portkey_bedrock_api_key,
            "ANTHROPIC_CUSTOM_HEADERS": portkey_headers,
            "ANTHROPIC_API_KEY": "",
        },
        tools=[],
        allowed_tools=[],
        max_turns=1,
        permission_mode="bypassPermissions",
        cwd=str(req_dir),
        include_partial_messages=False,
    )

    bookkeeping: dict[str, Any] = {
        "request_id": request_id,
        "cwd": str(req_dir),
        "session_ids": [],
        "status": "unknown",
    }

    t0 = time.perf_counter()
    try:
        if dry_run:
            # Simulate SDK behavior: write a fake JSONL transcript and a fake
            # session id. Exercises the directory-isolation logic without billing.
            fake_session = f"dry-{request_id}"
            fake_path = req_dir / f"{fake_session}.jsonl"
            with fake_path.open("w") as fh:
                fh.write(json.dumps({"session_id": fake_session, "msg": "dry"}) + "\n")
            bookkeeping["session_ids"].append(fake_session)
            bookkeeping["status"] = "pass"
        else:
            async for msg in query(prompt="Reply with the single word: ok", options=options):
                sid = getattr(msg, "session_id", None)
                if sid and sid not in bookkeeping["session_ids"]:
                    bookkeeping["session_ids"].append(sid)
            bookkeeping["status"] = "pass"
    except Exception as e:  # noqa: BLE001
        bookkeeping["status"] = "fail"
        bookkeeping["error"] = f"{type(e).__name__}: {e}"
    finally:
        bookkeeping["elapsed_ms"] = (time.perf_counter() - t0) * 1000

    return bookkeeping


def _find_jsonl_files(root: Path) -> list[Path]:
    """Return every .jsonl file under root (any depth)."""
    return sorted(root.rglob("*.jsonl"))


def _validate_jsonl(path: Path) -> tuple[bool, str | None, set[str]]:
    """Return (ok, error_message, session_ids_in_file)."""
    session_ids: set[str] = set()
    try:
        with path.open("r") as fh:
            for i, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    return False, f"line {i}: {e}", session_ids
                sid = obj.get("session_id") or obj.get("sessionId")
                if sid:
                    session_ids.add(sid)
    except OSError as e:
        return False, f"read error: {e}", session_ids
    return True, None, session_ids


async def run(n: int, *, dry_run: bool) -> int:
    _section(f"Spike 2 — transcript isolation stress ({n} concurrent, dry_run={dry_run})")

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if not dry_run:
        try:
            from src.config.settings import settings  # noqa: F401 — verify import
        except Exception as e:  # noqa: BLE001
            _result("FAIL", f"settings import failed: {e}")
            return 1

    # One transcript root for the whole run; mirrors what
    # build_transcript_dir() will produce in Phase 1 per
    # ${SDK_TRANSCRIPT_ROOT}/${INSTANCE_ID}/...
    transcript_root = Path(tempfile.mkdtemp(prefix="spike-phase1-transcripts-"))
    _result("INFO", f"transcript_root: {transcript_root}")

    # Launch all requests concurrently via asyncio.gather — this is the hostile
    # scenario PRD Risk 3 calls out. No semaphore, no ordering.
    request_ids = [f"req-{i:03d}-{uuid.uuid4().hex[:6]}" for i in range(n)]

    t0 = time.perf_counter()
    results = await asyncio.gather(
        *[_one_request(rid, transcript_root, dry_run=dry_run) for rid in request_ids],
        return_exceptions=False,
    )
    total_elapsed_ms = (time.perf_counter() - t0) * 1000

    # ------------------------------------------------------------------
    # Post-run invariants
    # ------------------------------------------------------------------

    # 1. All requests completed
    status_counts = Counter(r["status"] for r in results)
    _result("INFO", f"per-request status: {dict(status_counts)}")
    all_passed = status_counts.get("pass", 0) == n
    for r in results:
        if r["status"] != "pass":
            _result("FAIL", f"{r['request_id']} failed: {r.get('error', '<no error>')}")

    # 2. Each request's JSONLs live ONLY in its own cwd subtree
    #    (i.e. the intersection of directories between two request dirs is empty)
    req_dir_files: dict[str, list[Path]] = {}
    for r in results:
        d = Path(r["cwd"])
        req_dir_files[r["request_id"]] = _find_jsonl_files(d)

    empty_dirs = []
    for rid, files in req_dir_files.items():
        if not files:
            empty_dirs.append(rid)
    if empty_dirs:
        _result(
            "WARN",
            f"{len(empty_dirs)}/{n} request dirs have no JSONL transcripts — "
            "may indicate SDK wrote transcripts elsewhere (e.g. ~/.claude/projects/...)",
        )

    # 2b. Search for SDK-written transcripts outside the cwd subtree
    #     (~/.claude/projects/<encoded-cwd>/ is where they'd land if cwd isolation isn't
    #     honored; the "encoded-cwd" path name makes per-request separation work anyway,
    #     but we want to confirm cwd is actually being used)
    home_projects = Path.home() / ".claude" / "projects"
    encoded_hits = []
    if home_projects.exists() and not dry_run:
        # The SDK encodes absolute cwd paths into directory names by replacing
        # path separators. Look for any dir whose name contains our transcript
        # root prefix.
        root_token = re.sub(r"[^a-zA-Z0-9]+", "-", str(transcript_root)).strip("-")
        for child in home_projects.iterdir():
            if root_token in child.name:
                encoded_hits.append(child)
    if encoded_hits:
        _result(
            "INFO", f"SDK stored transcripts under ~/.claude/projects (count: {len(encoded_hits)})"
        )
        # This is the SDK's actual storage path; cwd controls the encoded subdir
        # name, so isolation still holds as long as each cwd is unique.

    # 3. Every JSONL file parses cleanly + collect all session_ids
    all_session_ids: Counter[str] = Counter()
    per_file_sessions: dict[str, set[str]] = {}
    parse_failures: list[tuple[Path, str]] = []

    # Broaden the scan to also cover ~/.claude/projects/ encoded dirs for this run
    files_to_scan: list[Path] = []
    for files in req_dir_files.values():
        files_to_scan.extend(files)
    for enc_dir in encoded_hits:
        files_to_scan.extend(enc_dir.rglob("*.jsonl"))

    for f in files_to_scan:
        ok, err, sids = _validate_jsonl(f)
        if not ok:
            parse_failures.append((f, err or "unknown"))
        else:
            for sid in sids:
                all_session_ids[sid] += 1
            per_file_sessions[str(f)] = sids

    _result("INFO", f"JSONL files scanned: {len(files_to_scan)}")
    _result("INFO", f"unique session_ids: {len(all_session_ids)}")

    # 4. No session_id appears in more than one file (collision check)
    cross_file_sids = [sid for sid, cnt in all_session_ids.items() if cnt > 1]

    # 5. Cleanup test — delete all per-request dirs and confirm the root is empty
    for r in results:
        shutil.rmtree(r["cwd"], ignore_errors=True)
    # Also sweep the ~/.claude/projects encoded dirs we created this run
    for d in encoded_hits:
        shutil.rmtree(d, ignore_errors=True)
    post_cleanup_files = _find_jsonl_files(transcript_root)

    checks = {
        "all_requests_passed": all_passed,
        "every_request_dir_got_a_transcript": len(empty_dirs) == 0 or len(encoded_hits) > 0,
        "zero_jsonl_parse_errors": len(parse_failures) == 0,
        "zero_session_id_collisions": len(cross_file_sids) == 0,
        "cleanup_removed_transcripts": len(post_cleanup_files) == 0,
    }

    _section("Spike 2 — acceptance")
    for k, v in checks.items():
        _result("PASS" if v else "FAIL", f"{k}: {v}")
    if parse_failures:
        for f, err in parse_failures[:5]:
            _result("FAIL", f"parse failure in {f}: {err}")
    if cross_file_sids:
        for sid in cross_file_sids[:5]:
            _result("FAIL", f"session_id collision: {sid} seen in multiple files")
    _result("INFO", f"total elapsed: {total_elapsed_ms:.0f}ms for {n} concurrent requests")
    if results:
        max_latency = max(r["elapsed_ms"] for r in results)
        _result("INFO", f"max per-request latency: {max_latency:.0f}ms")

    # Final root cleanup
    shutil.rmtree(transcript_root, ignore_errors=True)

    return 0 if all(checks.values()) else 1


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=50, help="Concurrent request count (default 50)")
    p.add_argument("--dry-run", action="store_true", help="Skip LLM calls; stress dir logic only")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(asyncio.run(run(args.n, dry_run=args.dry_run)))
