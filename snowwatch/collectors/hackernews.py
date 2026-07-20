"""Hacker News collector via the public Algolia search API (no auth)."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .. import config
from ..models import Signal
from .base import CollectorError, polite_get, truncate

_API = "https://hn.algolia.com/api/v1/search_by_date"


class HackerNewsCollector:
    name = "hackernews"

    def collect(self, client: httpx.Client) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        for term in config.QUERY_TERMS:
            try:
                resp = polite_get(
                    client,
                    _API,
                    params={
                        "query": term,
                        "tags": "(comment,story)",
                        "hitsPerPage": 50,
                    },
                )
            except CollectorError:
                raise
            for hit in resp.json().get("hits", []):
                sig = self._to_signal(hit, term)
                if sig is None or sig.url in seen:
                    continue
                seen.add(sig.url)
                signals.append(sig)
        return signals

    @staticmethod
    def _to_signal(hit: dict, term: str) -> Signal | None:
        object_id = hit.get("objectID")
        if not object_id:
            return None
        title = hit.get("title") or hit.get("story_title") or "(HN comment)"
        body = hit.get("comment_text") or hit.get("story_text") or hit.get("title") or ""
        if not body.strip():
            return None
        ts = hit.get("created_at_i")
        posted = (
            datetime.fromtimestamp(ts, tz=timezone.utc)
            if ts
            else datetime.now(timezone.utc)
        )
        return Signal(
            source="hackernews",
            url=f"https://news.ycombinator.com/item?id={object_id}",
            title=truncate(title, 200),
            text_excerpt=truncate(body),
            author=hit.get("author") or "unknown",
            posted_at=posted,
            matched_terms=[term],
            engagement=int(hit.get("points") or 0) + int(hit.get("num_comments") or 0),
        )
