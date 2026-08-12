"""Regression tests for the sandbox service's job execution and file handoff.

Backstory (nested outputs): ``collect_output_files`` scanned the job directory with
``Path.iterdir()``, which is not recursive. The coder is told to read its input
from ``outputs/<name>.csv``, so it writes its chart alongside, under
``outputs/plots/``. Those files were never collected, the job directory is
``rmtree``'d immediately after the run, and S3 upload is skipped when no
credentials are configured — so a successfully rendered 95KB PNG disappeared
with ``exit_code=0`` and no error logged anywhere. The user just saw no chart.

The sandbox is a separate service with no test runner of its own, so the module
is loaded by path here to keep the behaviour covered by the backend suite.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SANDBOX_SERVER = Path(__file__).resolve().parents[3] / "sandbox" / "server.py"

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"payload" * 8


@pytest.fixture(scope="module")
def sandbox_server(tmp_path_factory):
    """Load sandbox/server.py by path, with JOBS_DIR pointed at a temp dir."""
    if not SANDBOX_SERVER.exists():  # pragma: no cover - layout guard
        pytest.skip(f"sandbox server not found at {SANDBOX_SERVER}")

    import os

    # Importing the module runs _load_dotenv_for_local_runs against the real
    # sandbox/.env, so snapshot the environment and put it back afterwards
    # rather than letting a developer's local credentials leak into other tests.
    snapshot = dict(os.environ)
    os.environ["SANDBOX_JOBS_DIR"] = str(tmp_path_factory.mktemp("jobs_dir"))
    try:
        spec = importlib.util.spec_from_file_location("sandbox_server", SANDBOX_SERVER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        os.environ.clear()
        os.environ.update(snapshot)


@pytest.fixture
def job_dir(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')")
    return tmp_path


class TestNestedOutputCollection:
    def test_collects_a_chart_written_to_a_subdirectory(self, sandbox_server, job_dir):
        nested = job_dir / "outputs" / "plots"
        nested.mkdir(parents=True)
        (nested / "chart.png").write_bytes(PNG_BYTES)

        collected = sandbox_server.collect_output_files(str(job_dir))

        assert "outputs/plots/chart.png" in collected, (
            "a chart written under outputs/plots/ must come back; a non-recursive "
            "scan drops it and the job directory is deleted right afterwards"
        )
        assert base64.b64decode(collected["outputs/plots/chart.png"]) == PNG_BYTES

    def test_still_collects_top_level_files(self, sandbox_server, job_dir):
        (job_dir / "root.png").write_bytes(PNG_BYTES)

        assert "root.png" in sandbox_server.collect_output_files(str(job_dir))

    def test_nested_csv_is_collected(self, sandbox_server, job_dir):
        (job_dir / "outputs").mkdir()
        (job_dir / "outputs" / "results.csv").write_text("a,b\n1,2\n")

        assert "outputs/results.csv" in sandbox_server.collect_output_files(str(job_dir))

    def test_same_basename_at_two_depths_does_not_collide(self, sandbox_server, job_dir):
        (job_dir / "chart.png").write_bytes(PNG_BYTES)
        nested = job_dir / "outputs" / "plots"
        nested.mkdir(parents=True)
        (nested / "chart.png").write_bytes(PNG_BYTES + b"different")

        collected = sandbox_server.collect_output_files(str(job_dir))

        assert {"chart.png", "outputs/plots/chart.png"} <= set(collected)
        assert collected["chart.png"] != collected["outputs/plots/chart.png"]


class TestExclusions:
    def test_control_files_are_never_returned(self, sandbox_server, job_dir):
        (job_dir / "s3_helpers.py").write_text("# helper")
        (job_dir / "s3_info.json").write_text("{}")

        collected = sandbox_server.collect_output_files(str(job_dir))

        assert not {"main.py", "s3_helpers.py", "s3_info.json"} & set(collected)

    def test_uncollectable_extensions_are_skipped(self, sandbox_server, job_dir):
        (job_dir / "outputs").mkdir()
        (job_dir / "outputs" / "notes.txt").write_text("not an artifact")

        assert "outputs/notes.txt" not in sandbox_server.collect_output_files(str(job_dir))

    def test_files_already_uploaded_to_s3_are_skipped(self, sandbox_server, job_dir):
        nested = job_dir / "outputs"
        nested.mkdir()
        (nested / "chart.png").write_bytes(PNG_BYTES)
        (job_dir / "s3_results.json").write_text(
            json.dumps({"created": [{"bucket": "b", "key": "some/prefix/chart.png"}]})
        )

        collected = sandbox_server.collect_output_files(str(job_dir))

        assert "outputs/chart.png" not in collected, (
            "the file is already in S3; returning it inline duplicates the payload"
        )

    def test_a_nested_jobs_tree_is_not_harvested(self, sandbox_server, job_dir):
        """JOBS_DIR is relative, so a job's CWD can contain another job's tree."""
        other = job_dir / ".sandbox_jobs" / "other-job-id"
        other.mkdir(parents=True)
        (other / "secret.png").write_bytes(PNG_BYTES)

        collected = sandbox_server.collect_output_files(str(job_dir))

        assert not any(".sandbox_jobs" in name for name in collected), (
            "one job's response must never carry another job's files"
        )

    def test_files_over_the_inline_limit_are_skipped(self, sandbox_server, job_dir):
        (job_dir / "huge.png").write_bytes(b"x" * (1024 * 1024 + 1))

        assert "huge.png" not in sandbox_server.collect_output_files(str(job_dir))


class TestLocalDotenvLoading:
    """Running the sandbox directly on a host must still read sandbox/.env.

    Under Docker Compose the file is delivered as `env_file`, so its values are
    already in os.environ. The documented local setup runs
    `.venv/bin/python server.py`, where nothing read the file at all: editing it
    had no effect, every AWS variable came back unset, and the only clue was a
    debug-endpoint hint telling you to check that Compose was reading it.
    """

    def test_values_are_loaded_from_the_file(self, sandbox_server, tmp_path, monkeypatch):
        monkeypatch.delenv("AWS_DEFAULT_BUCKET", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("AWS_DEFAULT_BUCKET=from-dotenv\n")

        sandbox_server._load_dotenv_for_local_runs(env_file)

        assert os.environ["AWS_DEFAULT_BUCKET"] == "from-dotenv"

    def test_real_environment_wins_over_the_file(self, sandbox_server, tmp_path, monkeypatch):
        """Compose, shell exports and Vault must keep precedence."""
        monkeypatch.setenv("AWS_DEFAULT_BUCKET", "from-environment")
        env_file = tmp_path / ".env"
        env_file.write_text("AWS_DEFAULT_BUCKET=from-dotenv\n")

        sandbox_server._load_dotenv_for_local_runs(env_file)

        assert os.environ["AWS_DEFAULT_BUCKET"] == "from-environment"

    def test_missing_file_is_a_no_op(self, sandbox_server, tmp_path):
        sandbox_server._load_dotenv_for_local_runs(tmp_path / "absent.env")

    def test_inline_comments_are_stripped_by_the_parser(
        self, sandbox_server, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("AWS_S3_ADDRESSING_STYLE", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("AWS_S3_ADDRESSING_STYLE=auto     # auto | path | virtual\n")

        sandbox_server._load_dotenv_for_local_runs(env_file)

        assert os.environ["AWS_S3_ADDRESSING_STYLE"] == "auto"


class TestJobInterpreter:
    """Jobs must run under the interpreter that has requirements.txt installed.

    ``build_cmd`` hardcoded "python3". Inside the Docker image that resolves to
    the interpreter the dependencies were installed into, so it looked fine. The
    documented local setup runs the server from sandbox/.venv, where bare
    "python3" is a *different*, bare system interpreter — no matplotlib, numpy or
    pandas, despite all three being pinned in requirements.txt. The agent reacted
    by pip-installing them per job into a directory deleted moments later (one
    such install hit the job timeout, exit 124) or by hand-drawing charts in PIL.
    """

    def test_uses_the_running_interpreter_not_bare_python3(self, sandbox_server):
        cmd = sandbox_server.build_cmd("/tmp/job", None)

        assert cmd[0] == sys.executable, (
            f"jobs must run under {sys.executable}, the interpreter that has the "
            f"sandbox dependencies; got {cmd[0]!r}"
        )
        assert cmd[0] != "python3", (
            "bare 'python3' resolves against PATH, which is the system "
            "interpreter when the server runs from a virtualenv"
        )

    def test_runs_main_py_by_relative_path(self, sandbox_server):
        """cwd is set to the job dir, so the script path stays relative."""
        assert sandbox_server.build_cmd("/tmp/job", None)[1] == "main.py"

    def test_appends_caller_arguments(self, sandbox_server):
        cmd = sandbox_server.build_cmd("/tmp/job", ["--flag", "value"])

        assert cmd[-2:] == ["--flag", "value"]

    def test_no_arguments_is_handled(self, sandbox_server):
        assert sandbox_server.build_cmd("/tmp/job", None) == [sys.executable, "main.py"]
