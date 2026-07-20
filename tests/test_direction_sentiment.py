from __future__ import annotations

from datetime import datetime, timezone

from snowwatch import classifier
from snowwatch.models import Signal
from snowwatch.scoring import analyze, score_signal


def _signal(title: str, body: str = "") -> Signal:
    return Signal(
        source="reddit",
        url=f"https://example.com/{hash((title, body)) & 0xffff}",
        title=title,
        text_excerpt=body,
        author="x",
        posted_at=datetime.now(timezone.utc),
    )


def test_outbound_migration_scores_high():
    sig = _signal("We are migrating off Snowflake to cut cost")
    assert score_signal(sig) >= 45
    assert classifier.classify(sig) == classifier.MIGRATION_INTENT


def test_inbound_migration_not_displacement():
    sig = _signal("We are migrating to Snowflake from Redshift")
    score_signal(sig)
    assert classifier.classify(sig) == classifier.MIGRATION_INBOUND


def test_inbound_scores_below_outbound():
    inbound = _signal("moving to snowflake next quarter")
    outbound = _signal("moving off snowflake next quarter")
    assert score_signal(inbound) < score_signal(outbound)


def test_inbound_variants_mixed_case():
    for phrase in ["Migrating TO Snowflake", "SWITCHED TO snowflake", "Moving Onto Snowflake"]:
        sig = _signal(phrase)
        assert classifier.classify(sig) == classifier.MIGRATION_INBOUND, phrase


def test_outbound_variants_mixed_case():
    for phrase in ["Migrating OFF Snowflake", "Leaving Snowflake", "moving AWAY from snowflake"]:
        sig = _signal(phrase)
        assert classifier.classify(sig) == classifier.MIGRATION_INTENT, phrase


def test_positive_sentiment_suppresses_cost_pain():
    sig = _signal("Snowflake pricing is fair and we are happy with snowflake")
    score_signal(sig)
    assert classifier.classify(sig) != classifier.COST_PAIN


def test_positive_sentiment_suppresses_performance():
    sig = _signal("snowflake is great, no complaints", "the occasional slow query is fine")
    assert classifier.classify(sig) != classifier.PERFORMANCE_COMPLAINT


def test_genuine_cost_pain_still_detected():
    sig = _signal("Our snowflake bill is too expensive")
    assert classifier.classify(sig) == classifier.COST_PAIN


def test_analyze_flags():
    inbound = analyze("we are migrating to snowflake".lower())
    assert inbound.inbound is True
    positive = analyze("snowflake is great".lower())
    assert positive.positive is True
