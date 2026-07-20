"""Shared collector protocol and HTTP helpers."""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

import httpx

from .. import config
from ..models import Signal


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


def polite_get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    """GET with a courtesy delay and unified error translation."""
    time.sleep(config.REQUEST_DELAY_SECONDS)
    try:
        resp = client.get(url, **kwargs)
        resp.raise_for_status()
        return resp
    except httpx.HTTPError as exc:
        raise CollectorError(f"GET {url} failed: {exc}") from exc


def truncate(text: str, limit: int = 500) -> str:
    """Collapse whitespace and cap excerpt length."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"
