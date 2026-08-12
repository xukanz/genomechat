"""Regression tests — sandbox HTTP failures must report *why*, not just a code.

Backstory: ``_handle_sandbox_error`` logged and returned only the status code.
When the sandbox answered 422 (FastAPI telling us which RunReq field failed
validation), both the log line and the agent-facing string said nothing but
"returned error 422. Please try again." — so the agent retried the identical
malformed payload, and the wasted round trips pushed the turn past the client
timeout.

These tests pin two things: the response body reaches the caller, and a 4xx
tells the agent not to retry unchanged.
"""

from __future__ import annotations

import httpx
import pytest

from src.tools._sandbox_utils import describe_http_error, is_client_error


def _status_error(status: int, json_body: object = None, text: str = "") -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://sandbox:8080/run")
    if json_body is not None:
        response = httpx.Response(status, json=json_body, request=request)
    else:
        response = httpx.Response(status, text=text, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


class TestDescribeHttpError:
    def test_includes_fastapi_validation_detail(self):
        error = _status_error(
            422,
            {
                "detail": [
                    {
                        "loc": ["body", "s3_outputs", 0, "bucket"],
                        "msg": "Field required",
                        "type": "missing",
                    }
                ]
            },
        )

        described = describe_http_error(error)

        assert "422" in described
        assert "s3_outputs" in described, (
            "the offending field must survive into the message — naming it is the "
            "whole point, otherwise the agent cannot fix its own call"
        )
        assert "Field required" in described

    def test_falls_back_to_plain_text_body(self):
        described = describe_http_error(_status_error(500, text="Internal Server Error"))

        assert "500" in described
        assert "Internal Server Error" in described

    def test_bare_status_when_body_is_empty(self):
        assert describe_http_error(_status_error(503, text="")) == "503"

    def test_long_body_is_truncated(self):
        described = describe_http_error(_status_error(422, text="x" * 5000), limit=100)

        assert len(described) < 200
        assert "truncated" in described


class TestIsClientError:
    @pytest.mark.parametrize("status", [400, 404, 422, 499])
    def test_4xx_is_a_client_error(self, status):
        assert is_client_error(_status_error(status, text="nope"))

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_5xx_is_not_a_client_error(self, status):
        assert not is_client_error(_status_error(status, text="nope"))


class TestHandlerMessages:
    def test_422_names_the_field_and_discourages_blind_retry(self):
        from src.tools.execute_code import _handle_sandbox_error

        message = _handle_sandbox_error(
            _status_error(
                422,
                {"detail": [{"loc": ["body", "s3_outputs", 0, "bucket"], "msg": "Field required"}]},
            )
        )

        assert "422" in message
        assert "s3_outputs" in message
        assert "retrying unchanged" in message, (
            "a 4xx means the payload is wrong; the agent must be told not to "
            "replay it, which is exactly the loop that burned the turn's budget"
        )

    def test_500_still_invites_a_retry(self):
        from src.tools.execute_code import _handle_sandbox_error

        message = _handle_sandbox_error(_status_error(500, text="upstream exploded"))

        assert "500" in message
        assert "upstream exploded" in message
        assert "Please try again" in message

    def test_timeout_message_is_unchanged(self):
        from src.tools.execute_code import _handle_sandbox_error

        message = _handle_sandbox_error(httpx.ReadTimeout("timed out"))

        assert "timed out" in message.lower()
