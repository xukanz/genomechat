"""Regression tests — CLI request timeouts must outlast a real agent turn.

Backstory: the standard-mode client timeout was 300s, hardcoded in three
places (constructor plus both branches of /mode). A plain "chart this table"
turn took 323s, so httpx raised ReadTimeout 23s before the backend finished.
The run had already succeeded server-side; the client just threw it away.

``str(httpx.ReadTimeout())`` is the empty string, so the CLI's generic
handler rendered the whole thing as a bare "Error:" with no cause.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from cli import (
    DEEP_RESEARCH_TIMEOUT_SECONDS,
    STANDARD_TIMEOUT_SECONDS,
    AgentCLI,
    _timeout_for_mode,
)

# The turn that exposed the bug, in seconds. Timeouts must clear it with room.
OBSERVED_SLOW_TURN_SECONDS = 323


@pytest.fixture
def cli():
    with patch("cli.TokenStorage") as storage:
        storage.return_value.load_tokens.return_value = (None, None)
        yield AgentCLI()


class TestTimeoutValues:
    def test_standard_timeout_clears_the_observed_slow_turn(self):
        assert STANDARD_TIMEOUT_SECONDS > OBSERVED_SLOW_TURN_SECONDS, (
            f"a real single-chart turn took {OBSERVED_SLOW_TURN_SECONDS}s; a standard "
            f"timeout at or below that silently discards completed work"
        )

    def test_deep_research_gets_more_headroom_than_standard(self):
        assert DEEP_RESEARCH_TIMEOUT_SECONDS > STANDARD_TIMEOUT_SECONDS

    @pytest.mark.parametrize(
        "mode,expected",
        [
            ("standard", STANDARD_TIMEOUT_SECONDS),
            ("deep_research", DEEP_RESEARCH_TIMEOUT_SECONDS),
            ("anything-else", STANDARD_TIMEOUT_SECONDS),
        ],
    )
    def test_timeout_for_mode(self, mode, expected):
        assert _timeout_for_mode(mode) == expected


class TestNoDriftBetweenModeSwitches:
    """The three former hardcoded sites must now agree."""

    def test_constructor_matches_helper(self, cli):
        assert cli.timeout == _timeout_for_mode("standard")

    def test_switching_to_deep_and_back_keeps_values_in_sync(self, cli):
        cli.set_research_mode("deep")
        assert cli.research_mode == "deep_research"
        assert cli.timeout == DEEP_RESEARCH_TIMEOUT_SECONDS

        cli.set_research_mode("standard")
        assert cli.research_mode == "standard"
        assert cli.timeout == STANDARD_TIMEOUT_SECONDS

    def test_client_timeout_tracks_the_mode(self, cli):
        cli.set_research_mode("deep")
        # httpx stores the value per-operation; read wins for a streaming SSE call.
        assert cli.client.timeout.read == DEEP_RESEARCH_TIMEOUT_SECONDS


class TestEmptyErrorRegression:
    def test_read_timeout_stringifies_to_nothing(self):
        """Pins the property that made the original failure undiagnosable."""
        assert str(httpx.ReadTimeout("")) == ""
