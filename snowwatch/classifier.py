"""Single-category classification for signals.

Categories follow the phrase buckets used by scoring, resolved in priority order
so the strongest displacement signal wins the label. Inbound migration is its
own category so it stays visible in stats but out of the outreach digest.
"""

from __future__ import annotations

from .models import Signal
from .scoring import analyze

COST_PAIN = "COST_PAIN"
MIGRATION_INTENT = "MIGRATION_INTENT"
MIGRATION_INBOUND = "MIGRATION_INBOUND"
PERFORMANCE_COMPLAINT = "PERFORMANCE_COMPLAINT"
VENDOR_COMPARISON = "VENDOR_COMPARISON"
OTHER = "OTHER"

CATEGORIES: tuple[str, ...] = (
    COST_PAIN,
    MIGRATION_INTENT,
    MIGRATION_INBOUND,
    PERFORMANCE_COMPLAINT,
    VENDOR_COMPARISON,
    OTHER,
)

# Categories that represent active displacement pain, eligible for the digest's
# top-signals and outreach sections.
DISPLACEMENT_CATEGORIES: frozenset[str] = frozenset(
    {MIGRATION_INTENT, COST_PAIN, PERFORMANCE_COMPLAINT, VENDOR_COMPARISON}
)

# Resolution order: strongest buy-signal first.
_PRIORITY: list[tuple[str, str]] = [
    ("migration_intent", MIGRATION_INTENT),
    ("cost_pain", COST_PAIN),
    ("performance_complaint", PERFORMANCE_COMPLAINT),
    ("vendor_comparison", VENDOR_COMPARISON),
]


def classify(signal: Signal) -> str:
    """Return the single best category for a signal and store it on the signal."""
    analysis = analyze(signal.content)
    if analysis.inbound:
        category = MIGRATION_INBOUND
    else:
        category = OTHER
        for bucket, label in _PRIORITY:
            if bucket in analysis.buckets:
                category = label
                break
    signal.category = category
    return category
