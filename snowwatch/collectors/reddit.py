"""Reddit collector via public .json search endpoints (no auth).

Reddit rate-limits aggressively and rejects generic User-Agents; requests go
through ``polite_get`` which applies both the configured delay and the project
User-Agent.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .. import config
from ..models import Signal
from .base import CollectorError, polite_get, truncate


class RedditCollector:
    name = "reddit"

    def collect(self, client: httpx.Client) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        for subreddit in config.SUBREDDITS:
            for term in config.QUERY_TERMS:
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                try:
                    resp = polite_get(
                        client,
                        url,
                        params={
                            "q": term,
                            "restrict_sr": 1,
                            "sort": "new",
                            "limit": 25,
                            "t": "year",
                        },
                    )
                except CollectorError:
                    raise
                for child in resp.json().get("data", {}).get("children", []):
                    sig = self._to_signal(child.get("data", {}), term)
                    if sig is None or sig.url in seen:
                        continue
                    seen.add(sig.url)
                    signals.append(sig)
        return signals

    @staticmethod
    def _to_signal(post: dict, term: str) -> Signal | None:
        permalink = post.get("permalink")
        if not permalink:
            return None
        title = post.get("title") or "(reddit post)"
        body = post.get("selftext") or ""
        created = post.get("created_utc")
        posted = (
            datetime.fromtimestamp(float(created), tz=timezone.utc)
            if created
            else datetime.now(timezone.utc)
        )
        return Signal(
            source="reddit",
            url=f"https://www.reddit.com{permalink}",
            title=truncate(title, 200),
            text_excerpt=truncate(body or title),
            author=post.get("author") or "unknown",
            posted_at=posted,
            matched_terms=[term],
            engagement=int(post.get("score") or 0) + int(post.get("num_comments") or 0),
        )
