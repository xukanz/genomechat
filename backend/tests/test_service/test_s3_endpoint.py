"""Tests for pointing the S3 client at a self-hosted, S3-compatible server.

Without an endpoint override the only supported artifact store was real AWS, so
a developer with no AWS account got no artifact storage at all: generated charts
fell back to inline base64, capped at 1MB and paid for out of the agent's
context window, and nothing was persisted.

Addressing style is the subtle half. MinIO and friends are reached by host:port,
and boto3's default virtual-host addressing would turn a bucket into
`http://my-bucket.localhost:9000`, which does not resolve.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import src.service.s3 as s3_module


@pytest.fixture(autouse=True)
def reset_client_singleton():
    """get_s3_client caches a module-level client; drop it around each test."""
    s3_module._s3_client = None
    yield
    s3_module._s3_client = None


@pytest.fixture
def captured_boto():
    """Capture the kwargs handed to boto3.client without building a real one."""
    with patch.object(s3_module, "boto3") as boto3_mock:
        yield boto3_mock


def _configure(**overrides):
    """Patch settings attributes used by get_s3_client."""
    defaults = {
        "aws_default_region": "us-east-1",
        "aws_access_key_id": None,
        "aws_secret_access_key": None,
        "aws_session_token": None,
        "aws_endpoint_url": None,
        "aws_s3_addressing_style": "auto",
    }
    defaults.update(overrides)
    return patch.multiple(s3_module.settings, **defaults)


def _kwargs(boto3_mock) -> dict:
    return boto3_mock.client.call_args.kwargs


class TestEndpointOverride:
    def test_custom_endpoint_is_passed_through(self, captured_boto):
        with _configure(aws_endpoint_url="http://localhost:9000"):
            s3_module.get_s3_client()

        assert _kwargs(captured_boto)["endpoint_url"] == "http://localhost:9000"

    def test_no_endpoint_key_when_unset(self, captured_boto):
        with _configure(aws_endpoint_url=None):
            s3_module.get_s3_client()

        assert "endpoint_url" not in _kwargs(captured_boto), (
            "passing endpoint_url=None is fine, but passing an empty string is not; "
            "keep the key absent so boto3 resolves real AWS itself"
        )

    def test_region_and_credentials_still_apply(self, captured_boto):
        with _configure(
            aws_endpoint_url="http://localhost:9000",
            aws_default_region="eu-west-1",
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin",
        ):
            s3_module.get_s3_client()

        kwargs = _kwargs(captured_boto)
        assert kwargs["region_name"] == "eu-west-1"
        assert kwargs["aws_access_key_id"] == "minioadmin"
        assert kwargs["aws_secret_access_key"] == "minioadmin"


class TestAddressingStyle:
    def test_custom_endpoint_defaults_to_path_style(self, captured_boto):
        with _configure(aws_endpoint_url="http://localhost:9000"):
            s3_module.get_s3_client()

        style = _kwargs(captured_boto)["config"].s3["addressing_style"]
        assert style == "path", (
            "virtual-host addressing against a custom endpoint resolves buckets as "
            "http://<bucket>.localhost:9000, which does not exist"
        )

    def test_real_aws_keeps_boto3_auto(self, captured_boto):
        with _configure(aws_endpoint_url=None):
            s3_module.get_s3_client()

        assert _kwargs(captured_boto)["config"].s3["addressing_style"] == "auto"

    def test_explicit_style_overrides_the_default(self, captured_boto):
        with _configure(
            aws_endpoint_url="http://localhost:9000",
            aws_s3_addressing_style="virtual",
        ):
            s3_module.get_s3_client()

        assert _kwargs(captured_boto)["config"].s3["addressing_style"] == "virtual"


class TestResolvedProperty:
    @pytest.mark.parametrize(
        "endpoint,configured,expected",
        [
            (None, "auto", "auto"),
            ("http://localhost:9000", "auto", "path"),
            (None, "path", "path"),
            ("http://localhost:9000", "virtual", "virtual"),
        ],
    )
    def test_resolution_matrix(self, endpoint, configured, expected):
        with _configure(aws_endpoint_url=endpoint, aws_s3_addressing_style=configured):
            assert s3_module.settings.s3_addressing_style_resolved == expected


class TestMalformedConfigIsTolerated:
    """Values arrive from .env files, which different parsers clean differently.

    python-dotenv strips a trailing `# comment`; Docker Compose's env_file
    parser does not necessarily. botocore answers an unrecognised style with
    InvalidS3AddressingStyleError at client construction, so one stray comment
    would disable S3 entirely rather than just this one setting.
    """

    def test_inline_comment_is_stripped(self, captured_boto):
        with _configure(
            aws_endpoint_url="http://localhost:9000",
            aws_s3_addressing_style="auto     # auto | path | virtual",
        ):
            s3_module.get_s3_client()

        assert _kwargs(captured_boto)["config"].s3["addressing_style"] == "path"

    def test_inline_comment_on_an_explicit_style(self, captured_boto):
        with _configure(aws_s3_addressing_style="virtual # pick one"):
            s3_module.get_s3_client()

        assert _kwargs(captured_boto)["config"].s3["addressing_style"] == "virtual"

    def test_case_and_padding_are_normalised(self, captured_boto):
        with _configure(aws_s3_addressing_style="  PATH  "):
            s3_module.get_s3_client()

        assert _kwargs(captured_boto)["config"].s3["addressing_style"] == "path"

    def test_unrecognised_value_falls_back_instead_of_breaking_s3(self, captured_boto):
        with _configure(
            aws_endpoint_url="http://localhost:9000",
            aws_s3_addressing_style="nonsense",
        ):
            s3_module.get_s3_client()

        assert _kwargs(captured_boto)["config"].s3["addressing_style"] == "path"

    def test_endpoint_with_an_inline_comment_still_resolves(self, captured_boto):
        """Guards the sandbox-side normalisation contract from the backend too."""
        with _configure(aws_s3_addressing_style="", aws_endpoint_url=None):
            s3_module.get_s3_client()

        assert _kwargs(captured_boto)["config"].s3["addressing_style"] == "auto"


class TestClientIsStillCached:
    def test_second_call_reuses_the_singleton(self, captured_boto):
        with _configure(aws_endpoint_url="http://localhost:9000"):
            first = s3_module.get_s3_client()
            second = s3_module.get_s3_client()

        assert first is second
        assert captured_boto.client.call_count == 1
