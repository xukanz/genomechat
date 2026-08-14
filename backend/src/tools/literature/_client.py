"""HTTP access to the Europe PMC REST API.

This is the only module in the package that imports ``httpx``, so tests patch a
single target and the request/exception ladder exists once rather than being
inlined per tool.

Every failure is raised as :class:`LiteratureAPIError` carrying an
already-user-facing message. ``tools.py`` renders those as ``f"Error: {e}"`` so
the whole package shares one error prefix — see
``src/service/mcp/_result_helpers.py`` for why the prefix is load-bearing.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)

# EBI asks consumers of its public REST services to identify themselves so they
# can distinguish well-behaved clients from scrapers when load spikes.
USER_AGENT = "GenomeChat/0.1 (genomics research assistant; +Europe PMC REST)"


class LiteratureAPIError(Exception):
    """Europe PMC could not be reached, or returned a non-success status."""


def _base_url() -> str:
    return settings.europepmc_api_url.rstrip("/")


async def _get(
    path: str,
    params: Optional[dict[str, Any]] = None,
    accept: str = "application/json",
) -> httpx.Response:
    """Issue one GET against Europe PMC, mapping transport failures to a message.

    Args:
        path: Path relative to the API root, with a leading slash.
        params: Query parameters. Passed to httpx for encoding — never
            interpolated into the URL, so query values cannot break out.
        accept: Accept header. Must match the endpoint: the full-text endpoint
            serves XML and answers 406 to an ``application/json`` request.

    Returns:
        The successful response.

    Raises:
        LiteratureAPIError: On connection failure, timeout, or non-2xx status.
            HTTP status errors keep ``response`` reachable via ``__cause__`` so
            callers can special-case 404.
    """
    url = f"{_base_url()}{path}"
    timeout = float(settings.europepmc_timeout_seconds)
    headers = {"User-Agent": USER_AGENT, "Accept": accept}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response
    except httpx.TimeoutException as e:
        logger.warning("Europe PMC request timed out: %s", url)
        raise LiteratureAPIError(
            f"Request to Europe PMC timed out after {timeout:.0f}s. Try a narrower query."
        ) from e
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        logger.warning("Europe PMC returned HTTP %s for %s", status, url)
        raise LiteratureAPIError(f"Europe PMC returned HTTP {status}.") from e
    except httpx.ConnectError as e:
        logger.error("Could not connect to Europe PMC at %s: %s", url, e)
        raise LiteratureAPIError("Could not reach Europe PMC. Check network connectivity.") from e
    except httpx.HTTPError as e:
        logger.error("Europe PMC request failed for %s: %s", url, e, exc_info=True)
        raise LiteratureAPIError(f"Europe PMC request failed: {e}") from e


async def get_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET a JSON document from Europe PMC.

    Raises:
        LiteratureAPIError: On transport failure or a body that isn't JSON.
    """
    response = await _get(path, params)
    try:
        return response.json()
    except ValueError as e:
        logger.error("Europe PMC returned non-JSON for %s", path, exc_info=True)
        raise LiteratureAPIError("Europe PMC returned a malformed response.") from e


async def get_text(path: str, allow_404: bool = False) -> Optional[str]:
    """GET a text document (JATS XML) from Europe PMC.

    Args:
        path: Path relative to the API root.
        allow_404: When True, a 404 returns ``None`` instead of raising. Full
            text is only present for the open-access subset, so a miss there is
            an expected outcome rather than a tool failure.

    Returns:
        The response body, or ``None`` if the document is absent and
        ``allow_404`` is set.
    """
    try:
        response = await _get(path, accept="application/xml")
    except LiteratureAPIError as e:
        cause = e.__cause__
        if (
            allow_404
            and isinstance(cause, httpx.HTTPStatusError)
            and cause.response.status_code == 404
        ):
            logger.info("Europe PMC has no document at %s", path)
            return None
        raise
    return response.text
