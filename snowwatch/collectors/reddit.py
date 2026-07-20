"""Reddit collector with two modes.

When REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are set, it uses the official OAuth
API (client-credentials flow, token cached until expiry, rate-limit headers
honored). Without credentials it falls back to the public ``.json`` search
endpoints, which many cloud IPs are blocked from (403). The active mode is
logged. The collector interface is identical in both modes.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from .. import config
from ..models import Signal
from .base import CollectorError, polite_get, truncate

logger = logging.getLogger("snowwatch")

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_OAUTH_BASE = "https://oauth.reddit.com"
_PUBLIC_BASE = "https://www.reddit.com"
_TOKEN_SKEW_SECONDS = 30.0
_MAX_RETRIES = 3


class RedditCollector:
    name = "reddit"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        self._client_id = client_id if client_id is not None else config.REDDIT_CLIENT_ID
        self._client_secret = client_secret if client_secret is not None else config.REDDIT_CLIENT_SECRET
        self._token: str | None = None
        self._token_expiry: float = 0.0

    @property
    def _authenticated(self) -> bool:
        return bool(self._client_id and self._client_secret)

    def collect(self, client: httpx.Client) -> list[Signal]:
        if self._authenticated:
            logger.info("reddit: using authenticated OAuth API")
            return self._collect(client, self._oauth_search)
        logger.info("reddit: no credentials, using public .json fallback")
        return self._collect(client, self._public_search)

    def _collect(self, client: httpx.Client, search) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        for subreddit in config.SUBREDDITS:
            for term in config.QUERY_TERMS:
                for post in search(client, subreddit, term):
                    sig = self._to_signal(post, term)
                    if sig is None or sig.url in seen:
                        continue
                    seen.add(sig.url)
                    signals.append(sig)
        return signals

    # --- OAuth mode --------------------------------------------------------

    def _ensure_token(self, client: httpx.Client) -> str:
        if self._token and time.time() < self._token_expiry:
            return self._token
        time.sleep(config.REQUEST_DELAY_SECONDS)
        try:
            resp = client.post(
                _TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self._client_id or "", self._client_secret or ""),
                headers={"User-Agent": config.USER_AGENT},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise CollectorError(f"reddit token request failed: {exc}") from exc
        payload = resp.json()
        token = payload.get("access_token")
        if not token:
            raise CollectorError("reddit token response missing access_token")
        self._token = token
        self._token_expiry = time.time() + float(payload.get("expires_in", 3600)) - _TOKEN_SKEW_SECONDS
        return token

    def _oauth_search(self, client: httpx.Client, subreddit: str, term: str) -> list[dict]:
        token = self._ensure_token(client)
        url = f"{_OAUTH_BASE}/r/{subreddit}/search"
        params = {"q": term, "restrict_sr": 1, "sort": "new", "limit": 25, "t": "year"}
        for attempt in range(_MAX_RETRIES):
            time.sleep(config.REQUEST_DELAY_SECONDS)
            resp = client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}", "User-Agent": config.USER_AGENT},
            )
            if resp.status_code == 401:
                self._token = None
                token = self._ensure_token(client)
                continue
            if resp.status_code == 429:
                self._respect_rate_limit(resp, forced=True)
                continue
            try:
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise CollectorError(f"reddit search failed: {exc}") from exc
            self._respect_rate_limit(resp)
            return [c.get("data", {}) for c in resp.json().get("data", {}).get("children", [])]
        raise CollectorError("reddit search exceeded retry budget")

    @staticmethod
    def _respect_rate_limit(resp: httpx.Response, forced: bool = False) -> None:
        """Back off when Reddit signals the quota is exhausted."""
        remaining = resp.headers.get("x-ratelimit-remaining")
        reset = resp.headers.get("x-ratelimit-reset")
        try:
            if forced or (remaining is not None and float(remaining) < 1):
                delay = float(reset) if reset else config.REQUEST_DELAY_SECONDS
                time.sleep(min(delay, 60.0))
        except ValueError:
            time.sleep(config.REQUEST_DELAY_SECONDS)

    # --- Public fallback mode ---------------------------------------------

    def _public_search(self, client: httpx.Client, subreddit: str, term: str) -> list[dict]:
        url = f"{_PUBLIC_BASE}/r/{subreddit}/search.json"
        resp = polite_get(
            client,
            url,
            params={"q": term, "restrict_sr": 1, "sort": "new", "limit": 25, "t": "year"},
        )
        return [c.get("data", {}) for c in resp.json().get("data", {}).get("children", [])]

    # --- Normalization -----------------------------------------------------

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
            url=f"{_PUBLIC_BASE}{permalink}",
            title=truncate(title, 200),
            text_excerpt=truncate(body or title),
            author=post.get("author") or "unknown",
            posted_at=posted,
            matched_terms=[term],
            engagement=int(post.get("score") or 0) + int(post.get("num_comments") or 0),
        )
