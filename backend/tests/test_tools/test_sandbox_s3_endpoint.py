"""Tests for the sandbox-side S3 client honouring a custom endpoint.

The sandbox uploads directly from executed code via s3_helpers, so pointing only
the backend at a self-hosted server would leave every chart stranded inside the
job directory. This module mirrors the backend's endpoint handling; the two
cannot share code because the sandbox is a separate service that does not import
backend settings.

Loaded by path, since the sandbox ships no test runner of its own.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest

S3_HELPERS = Path(__file__).resolve().parents[3] / "sandbox" / "s3_helpers.py"

AWS_VARS = (
    "AWS_ENDPOINT_URL",
    "AWS_S3_ADDRESSING_STYLE",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_DEFAULT_REGION",
)


@pytest.fixture(scope="module")
def s3_helpers():
    if not S3_HELPERS.exists():  # pragma: no cover - layout guard
        pytest.skip(f"sandbox s3_helpers not found at {S3_HELPERS}")

    spec = importlib.util.spec_from_file_location("sandbox_s3_helpers", S3_HELPERS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def clean_aws_env():
    """s3_helpers reads os.environ directly, so isolate every test from the host."""
    saved = {name: os.environ.pop(name, None) for name in AWS_VARS}
    yield
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def _kwargs(boto3_mock) -> dict:
    return boto3_mock.client.call_args.kwargs


class TestSandboxEndpoint:
    def test_endpoint_is_passed_through(self, s3_helpers):
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:9000"

        with patch.object(s3_helpers, "boto3") as boto3_mock:
            s3_helpers.get_s3_client()

        assert _kwargs(boto3_mock)["endpoint_url"] == "http://localhost:9000"

    def test_unset_endpoint_becomes_none_not_empty_string(self, s3_helpers):
        with patch.object(s3_helpers, "boto3") as boto3_mock:
            s3_helpers.get_s3_client()

        assert _kwargs(boto3_mock)["endpoint_url"] is None, (
            "boto3 rejects an empty endpoint_url as a malformed URL rather than "
            "treating it as unset, which fails every call"
        )

    def test_empty_endpoint_is_normalised_to_none(self, s3_helpers):
        os.environ["AWS_ENDPOINT_URL"] = ""

        with patch.object(s3_helpers, "boto3") as boto3_mock:
            s3_helpers.get_s3_client()

        assert _kwargs(boto3_mock)["endpoint_url"] is None


class TestSandboxAddressingStyle:
    def test_custom_endpoint_defaults_to_path_style(self, s3_helpers):
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:9000"

        with patch.object(s3_helpers, "boto3") as boto3_mock:
            s3_helpers.get_s3_client()

        assert _kwargs(boto3_mock)["config"].s3["addressing_style"] == "path"

    def test_no_endpoint_keeps_auto(self, s3_helpers):
        with patch.object(s3_helpers, "boto3") as boto3_mock:
            s3_helpers.get_s3_client()

        assert _kwargs(boto3_mock)["config"].s3["addressing_style"] == "auto"

    def test_explicit_style_wins(self, s3_helpers):
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:9000"
        os.environ["AWS_S3_ADDRESSING_STYLE"] = "virtual"

        with patch.object(s3_helpers, "boto3") as boto3_mock:
            s3_helpers.get_s3_client()

        assert _kwargs(boto3_mock)["config"].s3["addressing_style"] == "virtual"

    def test_single_connection_pool_is_preserved(self, s3_helpers):
        """RLIMIT_NPROC in the sandbox makes extra connection threads fatal."""
        os.environ["AWS_ENDPOINT_URL"] = "http://localhost:9000"

        with patch.object(s3_helpers, "boto3") as boto3_mock:
            s3_helpers.get_s3_client()

        assert _kwargs(boto3_mock)["config"].max_pool_connections == 1
