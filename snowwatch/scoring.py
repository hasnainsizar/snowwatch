"""Rule-based relevance scoring, direction analysis, and company extraction.

Fully offline: no model calls. Scores range 0-100 and reward, in order,
explicit outbound migration intent, cost complaints, then softer negativity.
Inbound migration ("moving TO Snowflake") and positive sentiment are detected
and neutralized so they do not read as displacement pain.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from . import config
from .models import Signal

_WE_AT_RE = re.compile(r"\bwe(?:'re| are)? (?:at|with) ([A-Z][A-Za-z0-9&.\-]+(?: [A-Z][A-Za-z0-9&.\-]+)?)")
_TEAM_RE = re.compile(r"\b([A-Z][A-Za-z0-9&.\-]+(?: [A-Z][A-Za-z0-9&.\-]+)?)'s (?:data|analytics|engineering|platform) team")
_AT_COMPANY_RE = re.compile(r"\b(?:at|joined|work at|working at) ([A-Z][A-Za-z0-9&.\-]{2,}(?: [A-Z][A-Za-z0-9&.\-]+)?)")
_ORG_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]+(?: [A-Z][A-Za-z0-9&.\-]+)?)\s+(?:Inc|LLC|Ltd|Corp|Corporation|Technologies|Labs|Systems|Software|Analytics)\b"
)
# High-confidence context patterns; a single match is enough.
_CONTEXT_PATTERNS = (_WE_AT_RE, _TEAM_RE, _AT_COMPANY_RE, _ORG_SUFFIX_RE)

# Bare capitalized token(s); needs repetition to count as evidence.
_CAP_TOKEN_RE = re.compile(r"\b[A-Z][A-Za-z0-9&.\-]+(?: [A-Z][A-Za-z0-9&.\-]+)?\b")

_SUFFIX_RE = re.compile(r"[\s,]+(?:Inc|LLC|Ltd|Corp|Corporation|Co)\.?$", re.IGNORECASE)

# Buckets suppressed when a positive-sentiment phrase is present.
_POSITIVE_SUPPRESSED = ("cost_pain", "performance_complaint", "general_negativity")

# Buckets whose phrases are specific enough to establish the data-warehouse topic
# on their own, independent of the data-context vocabulary check.
_TOPIC_BUCKETS = frozenset({"migration_intent", "cost_pain", "performance_complaint"})

_SKILLS_CONTEXT_RE = [re.compile(p, re.IGNORECASE) for p in config.SKILLS_CONTEXT_PATTERNS]


def _is_job_source(source: str | None) -> bool:
    return bool(source) and source.startswith("jobs")


def _has_vendor_evaluation(content: str) -> bool:
    return any(p in content for p in config.VENDOR_EVALUATIVE_PHRASES)


def _is_skills_list(content: str) -> bool:
    return any(pattern.search(content) for pattern in _SKILLS_CONTEXT_RE)


def is_staffing_company(company: str | None) -> bool:
    """True when the company name reads as a staffing/consulting firm."""
    if not company:
        return False
    lowered = company.casefold()
    if any(indicator in lowered for indicator in config.STAFFING_INDICATORS):
        return True
    return any(firm in lowered for firm in config.STAFFING_KNOWN_FIRMS)


@dataclass(slots=True)
class Analysis:
    """Direction- and sentiment-aware view of a signal's phrase matches."""

    buckets: dict[str, list[str]]
    inbound: bool
    positive: bool
    off_topic: bool


def _has_data_context(content: str) -> bool:
    return any(term in content for term in config.DATA_CONTEXT_TERMS)


def matched_phrases(content: str) -> dict[str, list[str]]:
    """Return, per signal bucket, the configured phrases present in the text."""
    hits: dict[str, list[str]] = {}
    for bucket, phrases in config.SIGNAL_PHRASES.items():
        found = [p for p in phrases if p in content]
        if found:
            hits[bucket] = found
    return hits


def analyze(content: str, source: str | None = None) -> Analysis:
    """Resolve effective phrase buckets after direction, sentiment, and topic guards.

    Inbound (moving TO Snowflake) without an explicit outbound phrase drops the
    migration bucket; positive sentiment drops the pain buckets. A signal with no
    topic-establishing bucket and no data-warehouse vocabulary is off-topic (e.g.
    snow/weather or the CDP product): its buckets and inbound flag are cleared so
    it scores to OTHER. For job postings, a competitor mention in a skills list
    without evaluative language does not count as a vendor comparison.
    """
    raw = matched_phrases(content)
    outbound = "migration_intent" in raw
    inbound = any(p in content for p in config.MIGRATION_INBOUND_PHRASES) and not outbound
    positive = any(p in content for p in config.POSITIVE_CONTEXT_PHRASES)

    buckets = dict(raw)
    if inbound:
        buckets.pop("migration_intent", None)
    if positive:
        for bucket in _POSITIVE_SUPPRESSED:
            buckets.pop(bucket, None)
    if (
        "vendor_comparison" in buckets
        and _is_job_source(source)
        and not _has_vendor_evaluation(content)
        and _is_skills_list(content)
    ):
        buckets.pop("vendor_comparison", None)

    on_topic = inbound or bool(_TOPIC_BUCKETS & buckets.keys()) or _has_data_context(content)
    off_topic = not on_topic
    if off_topic:
        buckets = {}
    return Analysis(buckets=buckets, inbound=inbound, positive=positive, off_topic=off_topic)


def normalize_company(name: str) -> str:
    """Collapse whitespace and strip legal suffixes for dedupe comparison."""
    collapsed = " ".join(name.split())
    return _SUFFIX_RE.sub("", collapsed).strip(" ,.")


def _clean_candidate(raw: str) -> str:
    return " ".join(raw.split()).strip(" .,-")


def _is_valid_company(candidate: str, allow_acronym: bool) -> bool:
    if len(candidate) < 2:
        return False
    # Bare capitalization treats an all-caps token as a keyword/acronym, not a
    # name; only context evidence can promote one (e.g. "we at IBM").
    if not allow_acronym and candidate.isupper():
        return False
    denylist = {d.casefold() for d in config.COMPANY_DENYLIST}
    if candidate.casefold() in denylist:
        return False
    for token in candidate.split():
        bare = token.strip(".,").casefold()
        if bare in denylist:
            return False
        if token in config.COMPANY_STOPWORDS:
            return False
    return candidate not in config.COMPANY_STOPWORDS


def extract_company(text: str) -> str | None:
    """Extract a company name using confidence tiers.

    Tier 1: explicit context ("we at X", "X's data team", "at X", legal suffix)
    counts on a single match. Tier 2: bare capitalization must recur (2+ times)
    and is not trusted for all-caps keywords. Denylisted tech/vendor/SQL terms
    and common capitalized words are rejected at every tier.
    """
    for pattern in _CONTEXT_PATTERNS:
        for match in pattern.finditer(text):
            candidate = _clean_candidate(match.group(1))
            if _is_valid_company(candidate, allow_acronym=True):
                return candidate

    counts: Counter[str] = Counter()
    for match in _CAP_TOKEN_RE.finditer(text):
        candidate = _clean_candidate(match.group(0))
        if _is_valid_company(candidate, allow_acronym=False):
            counts[candidate] += 1
    for candidate, occurrences in counts.most_common():
        if occurrences >= 2:
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

    Also fills ``matched_terms`` (from effective buckets) and ``company`` when
    they are not already populated by the collector.
    """
    analysis = analyze(signal.content, signal.source)
    buckets = analysis.buckets

    if not signal.matched_terms:
        signal.matched_terms = sorted({p for phrases in buckets.values() for p in phrases})

    total = 0
    if "migration_intent" in buckets:
        total += config.WEIGHTS["migration_intent"]
    if "cost_pain" in buckets:
        total += config.WEIGHTS["cost_pain"]
    if "performance_complaint" in buckets:
        total += config.WEIGHTS["performance_complaint"]
    if "vendor_comparison" in buckets:
        total += config.WEIGHTS["vendor_comparison"]
    if "general_negativity" in buckets:
        total += config.WEIGHTS["general_negativity"]

    if analysis.inbound:
        total -= config.WEIGHTS["migration_inbound_penalty"]

    if signal.company is None:
        # Extract from signal text only; the author field is never a company source.
        signal.company = extract_company(f"{signal.title}\n{signal.text_excerpt}")
    # Reward a detected company only alongside real displacement context, so a
    # skills-list posting cannot clear the digest floor on the company bonus.
    if signal.company and buckets:
        total += config.WEIGHTS["company_detected"]

    signal.staffing_flag = is_staffing_company(signal.company)

    total += _recency_bonus(signal.posted_at)

    if signal.engagement >= 10:
        total += config.WEIGHTS["engagement_bonus"]
    elif signal.engagement >= 3:
        total += config.WEIGHTS["engagement_bonus"] // 2

    signal.score = max(0, min(100, total))
    return signal.score
