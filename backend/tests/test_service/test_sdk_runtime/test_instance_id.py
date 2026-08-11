"""Tests for sdk_runtime instance_id resolution + transcript helpers."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _restore_env():
    """Snapshot + restore env vars the resolver reads."""
    original = {
        k: os.environ.get(k)
        for k in ("INSTANCE_ID", "POD_NAME", "HOSTNAME")
    }
    yield
    for k, v in original.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_resolve_instance_id_explicit_override():
    from src.service.sdk_runtime import resolve_instance_id

    os.environ["INSTANCE_ID"] = "explicit-test-id"
    os.environ["POD_NAME"] = "should-be-ignored"
    os.environ["HOSTNAME"] = "should-be-ignored-too"

    assert resolve_instance_id() == "explicit-test-id"


def test_resolve_instance_id_pod_name_fallback():
    from src.service.sdk_runtime import resolve_instance_id

    os.environ.pop("INSTANCE_ID", None)
    os.environ["POD_NAME"] = "genomechat-backend-abc123"
    os.environ["HOSTNAME"] = "should-be-ignored"

    assert resolve_instance_id() == "genomechat-backend-abc123"


def test_resolve_instance_id_hostname_fallback():
    from src.service.sdk_runtime import resolve_instance_id

    os.environ.pop("INSTANCE_ID", None)
    os.environ.pop("POD_NAME", None)
    os.environ["HOSTNAME"] = "container-hostname-xyz"

    assert resolve_instance_id() == "container-hostname-xyz"


def test_resolve_instance_id_uuid_fallback():
    from src.service.sdk_runtime import resolve_instance_id

    for var in ("INSTANCE_ID", "POD_NAME", "HOSTNAME"):
        os.environ.pop(var, None)

    result = resolve_instance_id()
    assert result.startswith("local-")
    assert len(result) == len("local-") + 8  # uuid4 hex[:8]


def test_build_transcript_dir_unique_per_request(tmp_path, monkeypatch):
    """Each call with a new request_id produces a fresh, writable directory."""
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    # Patch the module-level instance id constant so we can assert path layout
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "testpod")

    d1 = sdk_runtime.build_transcript_dir("user:conv", request_id="req-001")
    d2 = sdk_runtime.build_transcript_dir("user:conv", request_id="req-002")

    assert d1.exists() and d1.is_dir()
    assert d2.exists() and d2.is_dir()
    assert d1 != d2
    assert d1.parts[-4:] == (tmp_path.name, "testpod", "user:conv", "req-001")
    assert d2.parts[-4:] == (tmp_path.name, "testpod", "user:conv", "req-002")


def test_build_transcript_dir_no_thread_fallback(tmp_path, monkeypatch):
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "testpod")

    d = sdk_runtime.build_transcript_dir("", request_id="req-001")
    assert d.parts[-2] == "_no_thread"


def test_transcript_projects_dir_matches_sdk_encoding(tmp_path):
    """The encoded projects_dir name must round-trip through the SDK's own key fn.

    If the SDK renames project_key_for_directory or changes the sanitization
    algorithm, this test fails — we catch the drift before production.
    """
    from src.service import sdk_runtime

    # Use a cwd that exists so realpath succeeds and is deterministic.
    cwd = tmp_path / "abc-def" / "request-123"
    cwd.mkdir(parents=True)

    # Our helper's output
    our_dir = sdk_runtime.transcript_projects_dir_for(cwd)

    # The SDK's own function on the same input
    from claude_agent_sdk._internal.sessions import (  # type: ignore[import-untyped]
        _get_projects_dir as sdk_get_projects_dir,
        project_key_for_directory as sdk_project_key,
    )
    expected = sdk_get_projects_dir() / sdk_project_key(str(cwd))

    assert our_dir == expected


def test_cleanup_request_artifacts_removes_both_paths(tmp_path, monkeypatch):
    """`finally`-block cleanup should sweep the anchor dir AND the projects dir."""
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "cleanuptest")

    # Create anchor dir (as build_transcript_dir would)
    anchor = sdk_runtime.build_transcript_dir("t1", request_id="r1")
    # Simulate SDK writing a transcript file to its projects dir
    projects_dir = sdk_runtime.transcript_projects_dir_for(anchor)
    projects_dir.mkdir(parents=True, exist_ok=True)
    fake_transcript = projects_dir / "session-abc.jsonl"
    fake_transcript.write_text('{"type":"test"}\n')

    assert anchor.exists()
    assert fake_transcript.exists()

    sdk_runtime.cleanup_request_artifacts(anchor)

    assert not anchor.exists()
    assert not fake_transcript.exists()
    assert not projects_dir.exists()


def test_cleanup_request_artifacts_is_quiet_on_missing(tmp_path, monkeypatch):
    """Cleanup on a never-used anchor must not raise."""
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "missingtest")

    # Explicitly does not exist
    sdk_runtime.cleanup_request_artifacts(tmp_path / "never-created")


def test_cleanup_orphans_sweeps_stale_projects_dirs(tmp_path, monkeypatch):
    """Old entries in ~/.claude/projects/ matching this instance are removed."""
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "orphantest")

    # Build two anchors (so projects_dir paths are deterministic under tmp_path)
    anchor1 = sdk_runtime.build_transcript_dir("t1", request_id="r1")
    anchor2 = sdk_runtime.build_transcript_dir("t2", request_id="r2")

    # Fake-populate the SDK projects dirs and age them backward
    import time
    for a in (anchor1, anchor2):
        pdir = sdk_runtime.transcript_projects_dir_for(a)
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "session.jsonl").write_text('{"x":1}\n')
        old = time.time() - 7200  # 2h ago, older than default 1h
        os.utime(pdir, (old, old))
        os.utime(a, (old, old))

    removed = sdk_runtime.cleanup_orphans(max_age_seconds=3600)

    # 2 projects_dirs + 2 anchor dirs = 4 removals expected
    assert removed == 4
    assert not sdk_runtime.transcript_projects_dir_for(anchor1).exists()
    assert not sdk_runtime.transcript_projects_dir_for(anchor2).exists()
    assert not anchor1.exists()
    assert not anchor2.exists()


def test_cleanup_orphans_does_not_sweep_other_instances(tmp_path, monkeypatch):
    """Entries from a different instance_id must not be touched by this instance."""
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))

    # Pretend we're instance "A" and create anchors under A
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "instanceA")
    anchor_a = sdk_runtime.build_transcript_dir("tA", request_id="rA")
    pdir_a = sdk_runtime.transcript_projects_dir_for(anchor_a)
    pdir_a.mkdir(parents=True, exist_ok=True)
    (pdir_a / "a.jsonl").write_text("{}\n")

    # Now impersonate instance "B" and create its own artifacts
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "instanceB")
    anchor_b = sdk_runtime.build_transcript_dir("tB", request_id="rB")
    pdir_b = sdk_runtime.transcript_projects_dir_for(anchor_b)
    pdir_b.mkdir(parents=True, exist_ok=True)
    (pdir_b / "b.jsonl").write_text("{}\n")

    # Age both
    import time
    old = time.time() - 7200
    for p in (anchor_a, anchor_b, pdir_a, pdir_b):
        os.utime(p, (old, old))

    # Run cleanup as instance B — A must be left alone
    removed = sdk_runtime.cleanup_orphans(max_age_seconds=3600)

    assert not anchor_b.exists()
    assert not pdir_b.exists()
    assert anchor_a.exists(), "instance A anchor must survive instance B's sweep"
    assert pdir_a.exists(), "instance A projects dir must survive instance B's sweep"

    # Cleanup A's leftovers ourselves so we don't pollute ~/.claude/projects/
    import shutil
    shutil.rmtree(pdir_a, ignore_errors=True)


def test_cleanup_orphans_preserves_recent_entries(tmp_path, monkeypatch):
    """Entries younger than max_age_seconds must NOT be swept."""
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "recenttest")

    anchor = sdk_runtime.build_transcript_dir("t", request_id="r")
    pdir = sdk_runtime.transcript_projects_dir_for(anchor)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "s.jsonl").write_text("{}\n")
    # mtime is fresh — default constructor sets it to "now"

    removed = sdk_runtime.cleanup_orphans(max_age_seconds=3600)

    assert removed == 0
    assert anchor.exists()
    assert pdir.exists()

    # cleanup
    import shutil
    shutil.rmtree(pdir, ignore_errors=True)


def test_cleanup_orphans_handles_missing_roots_gracefully(tmp_path, monkeypatch):
    """Neither root existing → no crash, returns 0."""
    from src.service import sdk_runtime

    monkeypatch.setattr(
        sdk_runtime.settings,
        "sdk_transcript_root",
        str(tmp_path / "never-created"),
    )
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "ghostinstance")

    assert sdk_runtime.cleanup_orphans(max_age_seconds=0) == 0
