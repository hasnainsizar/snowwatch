"""Shared collector protocol and HTTP helpers."""

from __future__ import annotations

import logging
import re
import time
from html import unescape
from typing import Protocol, runtime_checkable

import httpx

from .. import config
from ..logutil import redact, request_line
from ..models import Signal

logger = logging.getLogger("snowwatch")

_TAG_RE = re.compile(r"<[^>]+>")


class CollectorError(Exception):
    """Raised when a collector cannot complete. Callers log and continue."""


@runtime_checkable
class Collector(Protocol):
    """A source that yields normalized signals."""

    name: str

    def collect(self, client: httpx.Client) -> list[Signal]:
        """Fetch and normalize signals. May raise CollectorError."""
        ...


def make_client() -> httpx.Client:
    """HTTP client preconfigured with the project User-Agent and timeout."""
    return httpx.Client(
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )


def polite_get(client: httpx.Client, url: str, *, label: str = "http", **kwargs) -> httpx.Response:
    """GET with a courtesy delay and unified error translation.

    Logs one redacted request line per call; credentials never reach the log.
    """
    time.sleep(config.REQUEST_DELAY_SECONDS)
    logger.info("%s: GET %s", label, request_line(url, kwargs.get("params")))
    try:
        resp = client.get(url, **kwargs)
        resp.raise_for_status()
        return resp
    except httpx.HTTPError as exc:
        raise CollectorError(f"GET {redact(url)} failed: {redact(str(exc))}") from exc


def strip_html(text: str) -> str:
    """Strip tags, decode entities (e.g. &#x2F;), and collapse whitespace."""
    return " ".join(unescape(_TAG_RE.sub(" ", text)).split())


def truncate(text: str, limit: int = 500) -> str:
    """Normalize to plain text (HTML stripped) and cap length."""
    cleaned = strip_html(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"
