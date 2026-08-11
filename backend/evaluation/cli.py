"""Offline trajectory capture CLI.

Two subcommands only — per Phase 0 scope revision:

    python -m backend.evaluation.cli bootstrap --out <path>
    python -m backend.evaluation.cli run --dataset <path> --backend langchain \
                                        --out <path> [--concurrency 4]

No judge, no rubric, no compare, no reports. The JSONL output IS the artifact.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.settings import settings

logger = logging.getLogger(__name__)


def _commit_sha() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
        return sha.decode().strip()
    except Exception:
        return "unknown"


def _settings_hash() -> str:
    """Hash of non-secret settings for manifest reproducibility.

    Deliberately excludes any key containing 'key', 'secret', 'password',
    'token', or 'auth' so the manifest can be shared safely.
    """
    redacted_substrings = ("key", "secret", "password", "token", "auth")
    snapshot: dict[str, Any] = {}
    for name, value in sorted(settings.model_dump().items()):
        lower = name.lower()
        if any(bad in lower for bad in redacted_substrings):
            continue
        try:
            json.dumps(value, default=str)
            snapshot[name] = value
        except Exception:
            continue
    blob = json.dumps(snapshot, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def _build_manifest(backend: str, total: int) -> dict[str, Any]:
    from src.config.agents import AGENT_LLM_MAP

    return {
        "backend": backend,
        "commit_sha": _commit_sha(),
        "settings_hash": _settings_hash(),
        "model_versions": {
            agent: f"{prov}:{model}" for agent, (prov, model) in AGENT_LLM_MAP.items()
        },
        "total_queries": total,
        "captured_at": datetime.now(tz=timezone.utc).isoformat(),
        "schema_version": "1",
    }


async def _run(
    dataset: Path,
    out: Path,
    backend: str,
    orchestrator_backend: str,
    concurrency: int,
) -> int:
    from .harness import replay

    if not dataset.exists():
        raise FileNotFoundError(dataset)

    out.parent.mkdir(parents=True, exist_ok=True)
    records = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    if not records:
        raise RuntimeError(f"Dataset at {dataset} is empty.")

    logger.info(
        "Replaying %d queries against coder=%s orchestrator=%s (concurrency=%d)",
        len(records),
        backend,
        orchestrator_backend,
        concurrency,
    )

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _one(record: dict) -> dict:
        async with semaphore:
            try:
                result = await replay(
                    record,
                    backend=backend,
                    orchestrator_backend=orchestrator_backend,
                )
                return {
                    "query_record": record,
                    "response": result.response,
                    "spans": result.spans,
                    "duration_ms": result.duration_ms,
                    "cost_usd": result.cost_usd,
                    "backend": result.backend,
                    "orchestrator_backend": orchestrator_backend,
                    "model_versions": result.model_versions,
                    "captured_at": datetime.now(tz=timezone.utc).isoformat(),
                }
            except Exception as e:
                logger.exception("replay failed for query: %s", record.get("query", "")[:80])
                return {
                    "query_record": record,
                    "response": "",
                    "spans": [],
                    "duration_ms": 0.0,
                    "cost_usd": 0.0,
                    "backend": backend,
                    "orchestrator_backend": orchestrator_backend,
                    "model_versions": {},
                    "captured_at": datetime.now(tz=timezone.utc).isoformat(),
                    "error": str(e),
                }

    results = await asyncio.gather(*(_one(r) for r in records))

    with out.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    manifest_path = out.with_suffix(".manifest.json")
    manifest = _build_manifest(backend, len(results))
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info("Wrote %d replays to %s; manifest at %s", len(results), out, manifest_path)

    # Phase 0 exit smoke check — see plan task 25.
    passed, failed = _smoke_check(out)
    print(f"smoke check: {passed}/{passed + failed} trajectories valid", flush=True)
    return 0 if failed == 0 else 2


def _smoke_check(output_path: Path) -> tuple[int, int]:
    """Validate every JSONL record against the Phase 0 exit criteria.

    - parses as JSON
    - non-empty `response`
    - at least one span with `name` matching `agent.node.*`
    - at least one span with `name == "gen_ai.chat"`

    Returns (passed, failed).
    """
    passed = 0
    failed = 0
    for idx, line in enumerate(output_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception as e:
            logger.error("smoke: record %d failed to parse: %s", idx, e)
            failed += 1
            continue
        if rec.get("error"):
            logger.error("smoke: record %d had replay error: %s", idx, rec["error"])
            failed += 1
            continue
        response = rec.get("response", "") or ""
        spans = rec.get("spans", []) or []
        has_node = any(
            isinstance(s, dict) and s.get("name", "").startswith("agent.node.") for s in spans
        )
        has_llm = any(isinstance(s, dict) and s.get("name") == "gen_ai.chat" for s in spans)
        if not response.strip() or not has_node or not has_llm:
            logger.error(
                "smoke: record %d invalid (response=%s, node=%s, llm=%s)",
                idx,
                bool(response.strip()),
                has_node,
                has_llm,
            )
            failed += 1
        else:
            passed += 1
    return passed, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backend.evaluation.cli", description="Trajectory capture harness (Phase 0)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    boot = sub.add_parser("bootstrap", help="Build a baseline dataset from consented conversations")
    boot.add_argument("--out", required=True, help="Output JSONL path")

    run = sub.add_parser("run", help="Replay a dataset and capture trajectories")
    run.add_argument("--dataset", required=True, help="Input JSONL dataset")
    run.add_argument(
        "--backend",
        default="langchain",
        choices=["langchain", "sdk"],
        help="Coder worker backend (langchain | sdk)",
    )
    run.add_argument(
        "--orchestrator-backend",
        default="langchain",
        choices=["langchain", "sdk"],
        help=(
            "Orchestrator backend (langchain | sdk). Phase 2 Workstream B "
            "evaluation requires four runs covering the 2x2 matrix: "
            "(coder=LC, orch=LC), (coder=SDK, orch=LC), "
            "(coder=LC, orch=SDK), (coder=SDK, orch=SDK)."
        ),
    )
    run.add_argument("--out", required=True, help="Output JSONL path")
    run.add_argument("--concurrency", type=int, default=4, help="Max concurrent replays")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "bootstrap":
        from .datasets import bootstrap

        count = bootstrap.run(args.out)
        print(f"Wrote {count} records to {args.out}")
        return 0
    if args.command == "run":
        return asyncio.run(
            _run(
                Path(args.dataset),
                Path(args.out),
                args.backend,
                args.orchestrator_backend,
                args.concurrency,
            )
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
