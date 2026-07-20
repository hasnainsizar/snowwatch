"""Single-category classification for signals.

Categories follow the same phrase buckets used by scoring, resolved in priority
order so the strongest displacement signal wins the label.
"""

from __future__ import annotations

from .models import Signal
from .scoring import matched_phrases

COST_PAIN = "COST_PAIN"
MIGRATION_INTENT = "MIGRATION_INTENT"
PERFORMANCE_COMPLAINT = "PERFORMANCE_COMPLAINT"
VENDOR_COMPARISON = "VENDOR_COMPARISON"
OTHER = "OTHER"

CATEGORIES: tuple[str, ...] = (
    COST_PAIN,
    MIGRATION_INTENT,
    PERFORMANCE_COMPLAINT,
    VENDOR_COMPARISON,
    OTHER,
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
    hits = matched_phrases(signal.content)
    category = OTHER
    for bucket, label in _PRIORITY:
        if bucket in hits:
            category = label
            break
    signal.category = category
    return category
