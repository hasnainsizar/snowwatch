from __future__ import annotations

from datetime import datetime, timezone

import httpx

from snowwatch import classifier, config
from snowwatch.collectors.jobs import StubJobSource
from snowwatch.models import Signal
from snowwatch.scoring import analyze, score_signal

# Real 30-day digest excerpt that scored 57 MIGRATION_INTENT: the ambiguous
# "Snowflake Migration" headline masked an explicitly inbound body.
MILESTONE_TITLE = "Snowflake Migration Data Architect"
MILESTONE_EXCERPT = (
    "Snowflake Migration Data Architect Onsite in Burbank CA 9 Months Contract "
    "Summary Seeking a Senior level Data Analyst/Data Architect to support a "
    "critical enterprise data migration initiative, transitioning our data "
    "platform from Microsoft SQL Server to Snowflake. This resource will design "
    "scalable data architectures, build robust migration pipelines, and enable "
    "modern self-service analytics through Tableau and Power BI."
)


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


def test_ambiguous_phrases_are_migration_intent_phrases():
    # The ambiguity guard only bites on phrases the intent bucket actually
    # matches; a rename on one side would silently disable it.
    assert config.AMBIGUOUS_MIGRATION_PHRASES <= set(config.SIGNAL_PHRASES["migration_intent"])


def test_milestone_posting_classifies_inbound():
    sig = _signal(MILESTONE_TITLE, MILESTONE_EXCERPT)
    sig.source = "jobs"
    score_signal(sig)
    assert classifier.classify(sig) == classifier.MIGRATION_INBOUND


def test_milestone_posting_falls_below_digest_floor():
    sig = _signal(MILESTONE_TITLE, MILESTONE_EXCERPT)
    sig.source = "jobs"
    assert score_signal(sig) < config.DIGEST_MIN_SCORE


def test_from_x_to_snowflake_is_inbound():
    phrases = [
        "transitioning our data platform from Microsoft SQL Server to Snowflake",
        "migrating our warehouse from Redshift to Snowflake",
        "a migration from Teradata to Snowflake",
        "moving the reporting stack from BigQuery to Snowflake",
        "porting legacy SQL Server workloads to Snowflake",
    ]
    for phrase in phrases:
        sig = _signal("Data engineer", phrase)
        score_signal(sig)
        assert classifier.classify(sig) == classifier.MIGRATION_INBOUND, phrase


def test_to_snowflake_beats_ambiguous_migration_term():
    sig = _signal(
        "Snowflake migration engineer",
        "Own the snowflake migration: we are transitioning our warehouse from Oracle to Snowflake.",
    )
    score_signal(sig)
    assert classifier.classify(sig) == classifier.MIGRATION_INBOUND
    assert sig.score < config.DIGEST_MIN_SCORE


def test_inbound_construction_takes_the_penalty():
    inbound = _signal("Snowflake migration lead", "migrating our data warehouse from Redshift to Snowflake")
    ambiguous = _signal("Snowflake migration lead", "own the snowflake migration roadmap for the data warehouse")
    assert score_signal(inbound) < score_signal(ambiguous)


def test_outbound_keeps_priority_over_inbound_construction():
    sig = _signal(
        "Warehouse replatform",
        "We are migrating off Snowflake this year, reversing last year's move from Redshift to Snowflake.",
    )
    assert classifier.classify(sig) == classifier.MIGRATION_INTENT


def test_from_snowflake_to_competitor_is_not_inbound():
    sig = _signal("Warehouse move", "we are moving from snowflake to databricks next quarter")
    assert classifier.classify(sig) != classifier.MIGRATION_INBOUND


def test_stub_migration_text_still_scores_high():
    signals = StubJobSource().fetch(httpx.Client(), [])
    migration = next(s for s in signals if "Migration" in s.title)
    assert score_signal(migration) >= 90
    assert classifier.classify(migration) == classifier.MIGRATION_INTENT


def test_analyze_flags():
    inbound = analyze("we are migrating to snowflake".lower())
    assert inbound.inbound is True
    positive = analyze("snowflake is great".lower())
    assert positive.positive is True
