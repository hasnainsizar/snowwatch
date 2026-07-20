"""Stack Exchange collector via the public API 2.3 (no key required).

Searches Stack Overflow and dba.stackexchange for Snowflake pain questions. A
STACKEXCHANGE_KEY, if present, only raises the request quota. The API contract
mandates honoring the ``backoff`` field between calls; ``quota_remaining`` is
watched so a run stops before exhausting the daily quota.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from html import unescape

import httpx

from .. import config
from ..models import Signal
from .base import CollectorError, polite_get, truncate

logger = logging.getLogger("snowwatch")

_API = "https://api.stackexchange.com/2.3/search/advanced"
_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(html: str) -> str:
    """Remove tags, unescape entities, and collapse whitespace."""
    return " ".join(unescape(_TAG_RE.sub(" ", html)).split())


class StackExchangeCollector:
    name = "stackexchange"

    def __init__(self, key: str | None = None) -> None:
        self._key = key if key is not None else config.STACKEXCHANGE_KEY

    def collect(self, client: httpx.Client) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        for site in config.STACKEXCHANGE_SITES:
            for term in config.STACKEXCHANGE_QUERY_TERMS:
                payload = self._search(client, site, term)
                for item in payload.get("items", []):
                    sig = self._to_signal(item, term)
                    if sig is None or sig.url in seen:
                        continue
                    seen.add(sig.url)
                    signals.append(sig)

                backoff = payload.get("backoff")
                if backoff:
                    time.sleep(min(float(backoff), 60.0))

                remaining = payload.get("quota_remaining")
                if remaining is not None and int(remaining) <= config.STACKEXCHANGE_QUOTA_FLOOR:
                    logger.warning(
                        "stackexchange: quota nearly exhausted (%s remaining), stopping early",
                        remaining,
                    )
                    return signals
        return signals

    def _search(self, client: httpx.Client, site: str, term: str) -> dict:
        params = {
            "q": term,
            "site": site,
            "filter": config.STACKEXCHANGE_FILTER,
            "sort": "relevance",
            "order": "desc",
            "pagesize": config.STACKEXCHANGE_PAGESIZE,
        }
        if self._key:
            params["key"] = self._key
        resp = polite_get(client, _API, params=params)
        try:
            return resp.json()
        except ValueError as exc:
            raise CollectorError(f"stackexchange returned non-JSON: {exc}") from exc

    @staticmethod
    def _to_signal(item: dict, term: str) -> Signal | None:
        link = item.get("link")
        if not link:
            return None
        title = strip_html(item.get("title") or "") or "(stackexchange question)"
        body = strip_html(item.get("body") or "")
        created = item.get("creation_date")
        posted = (
            datetime.fromtimestamp(int(created), tz=timezone.utc)
            if created
            else datetime.now(timezone.utc)
        )
        owner = item.get("owner") or {}
        return Signal(
            source="stackexchange",
            url=link,
            title=truncate(title, 200),
            text_excerpt=truncate(body or title),
            author=owner.get("display_name") or "unknown",
            posted_at=posted,
            matched_terms=[term],
            engagement=int(item.get("score") or 0) + int(item.get("answer_count") or 0),
        )
