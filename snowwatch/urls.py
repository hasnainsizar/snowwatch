"""URL canonicalization for dedupe.

Collected links carry per-request tracking noise: Adzuna rebuilds its landing
URLs with a fresh ``se`` token on every search, so the same ad looks like a new
signal on every collection run. Canonicalization reduces a URL to the stable
identity of the thing it points at, and that canonical form is what the dedupe
key hashes.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import config

# Host used by the offline stub job source. Lives here because canonicalization
# is what keeps stub identity separate from live postings; models.STUB_SOURCE is
# the matching source tag.
STUB_URL_HOST = "jobs.example.com"

_ADZUNA_HOST_RE = re.compile(r"(?:^|\.)adzuna\.[a-z.]+$")
# Both link shapes Adzuna returns; the numeric id is the stable ad identity.
_ADZUNA_AD_RE = re.compile(r"/(?:land/ad|details)/(\d+)")


def _is_tracking_param(name: str) -> bool:
    lowered = name.lower()
    if lowered in config.TRACKING_QUERY_PARAMS:
        return True
    return any(lowered.startswith(prefix) for prefix in config.TRACKING_QUERY_PREFIXES)


def _clean_query(query: str) -> str:
    """Drop tracking params and sort the rest so ordering cannot vary the key."""
    kept = [
        (k, v) for k, v in parse_qsl(query, keep_blank_values=True) if not _is_tracking_param(k)
    ]
    return urlencode(sorted(kept))


def canonical_url(url: str) -> str:
    """Reduce a URL to a stable dedupe key.

    Stub postings collapse to ``stub:<path>`` and Adzuna postings to
    ``adzuna:<ad id>``, the latter because their landing URLs are regenerated
    per request. The two namespaces are disjoint, so a stub can never share a
    dedupe key with a live posting and be merged into one. Every other URL keeps
    scheme, host, path, and its meaningful query params (Hacker News and Stack
    Exchange identify posts that way), with tracking params, fragments,
    ``www.``, and a trailing slash removed. The result is lowercased so case
    alone never splits a signal.
    """
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    if host == STUB_URL_HOST:
        return f"stub:{parts.path.strip('/').lower()}"
    if _ADZUNA_HOST_RE.search(host):
        match = _ADZUNA_AD_RE.search(parts.path)
        if match:
            return f"adzuna:{match.group(1)}"
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme, host, path, _clean_query(parts.query), "")).lower()


def url_hash(url: str) -> str:
    """Storage dedupe key: SHA-256 over the canonical form of a URL."""
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()
