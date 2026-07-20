"""Rule-based relevance scoring and company-name extraction.

Fully offline: no model calls. Scores range 0-100 and reward, in order,
explicit migration intent, cost complaints, then softer negativity signals.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from . import config
from .models import Signal

_WE_AT_RE = re.compile(r"\bwe(?:'re)? at ([A-Z][A-Za-z0-9&.\-]+(?: [A-Z][A-Za-z0-9&.\-]+)?)")
_AT_COMPANY_RE = re.compile(r"\b(?:at|for|from|joined|work at) ([A-Z][A-Za-z0-9&.\-]{2,}(?: [A-Z][A-Za-z0-9&.\-]+)?)")
_ORG_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]+(?: [A-Z][A-Za-z0-9&.\-]+)?)\s+(?:Inc|LLC|Ltd|Corp|Corporation|Technologies|Labs|Systems|Software|Analytics)\b"
)


def matched_phrases(content: str) -> dict[str, list[str]]:
    """Return, per signal bucket, the configured phrases present in the text."""
    hits: dict[str, list[str]] = {}
    for bucket, phrases in config.SIGNAL_PHRASES.items():
        found = [p for p in phrases if p in content]
        if found:
            hits[bucket] = found
    return hits


def extract_company(text: str) -> str | None:
    """Best-effort company name from free text using capitalization heuristics.

    Tries explicit "we at X" / "at X" patterns first, then a legal-suffix
    pattern. Returns None when nothing survives the stopword filter.
    """
    for pattern in (_WE_AT_RE, _AT_COMPANY_RE, _ORG_SUFFIX_RE):
        for match in pattern.finditer(text):
            candidate = match.group(1).strip(" .,-")
            head = candidate.split()[0]
            if head in config.COMPANY_STOPWORDS:
                continue
            if candidate in config.COMPANY_STOPWORDS:
                continue
            return candidate
    return None


def _recency_bonus(posted_at: datetime) -> int:
    """Full bonus for the last 3 days, tapering to zero past 14 days."""
    now = datetime.now(timezone.utc)
    posted = posted_at if posted_at.tzinfo else posted_at.replace(tzinfo=timezone.utc)
    age_days = (now - posted).total_seconds() / 86400
    if age_days <= 3:
        return config.WEIGHTS["recency_bonus"]
    if age_days >= 14:
        return 0
    fraction = 1 - (age_days - 3) / 11
    return round(config.WEIGHTS["recency_bonus"] * fraction)


def score_signal(signal: Signal) -> int:
    """Compute the 0-100 relevance score and mutate the signal in place.

    Also fills ``matched_terms`` (from configured phrases) and ``company`` when
    they are not already populated by the collector.
    """
    content = signal.content
    hits = matched_phrases(content)

    if not signal.matched_terms:
        signal.matched_terms = sorted({p for phrases in hits.values() for p in phrases})

    total = 0
    if "migration_intent" in hits:
        total += config.WEIGHTS["migration_intent"]
    if "cost_pain" in hits:
        total += config.WEIGHTS["cost_pain"]
    if "performance_complaint" in hits:
        total += config.WEIGHTS["performance_complaint"]
    if "vendor_comparison" in hits:
        total += config.WEIGHTS["vendor_comparison"]
    if "general_negativity" in hits:
        total += config.WEIGHTS["general_negativity"]

    if signal.company is None:
        signal.company = extract_company(f"{signal.title}\n{signal.text_excerpt}")
    if signal.company:
        total += config.WEIGHTS["company_detected"]

    total += _recency_bonus(signal.posted_at)

    if signal.engagement >= 10:
        total += config.WEIGHTS["engagement_bonus"]
    elif signal.engagement >= 3:
        total += config.WEIGHTS["engagement_bonus"] // 2

    signal.score = max(0, min(100, total))
    return signal.score
