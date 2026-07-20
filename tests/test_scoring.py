from __future__ import annotations

from datetime import datetime, timedelta, timezone

from snowwatch import config
from snowwatch.models import Signal
from snowwatch.scoring import extract_company, score_signal


def test_migration_outranks_cost(migration_signal, cost_signal):
    assert score_signal(migration_signal) > score_signal(cost_signal)


def test_cost_outranks_neutral(cost_signal, neutral_signal):
    assert score_signal(cost_signal) > score_signal(neutral_signal)


def test_score_is_bounded(migration_signal):
    score = score_signal(migration_signal)
    assert 0 <= score <= 100


def test_matched_terms_populated(cost_signal):
    score_signal(cost_signal)
    assert "snowflake bill" in cost_signal.matched_terms
    assert "too expensive" in cost_signal.matched_terms


def test_recency_bonus_decays():
    def make(age_days: int) -> Signal:
        return Signal(
            source="hackernews",
            url=f"https://news.ycombinator.com/item?id={age_days}",
            title="Snowflake costs too expensive",
            text_excerpt="snowflake bill is too expensive",
            author="x",
            posted_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        )

    fresh = score_signal(make(1))
    stale = score_signal(make(30))
    assert fresh > stale


def test_extract_company_we_at():
    assert extract_company("We at Northwind Analytics are leaving") == "Northwind Analytics"


def test_extract_company_ignores_stopwords():
    assert extract_company("We at Snowflake are fine") is None


def test_extract_company_none_when_absent():
    assert extract_company("just some lowercase text with no orgs") is None


def test_company_detection_adds_points():
    base = Signal(
        source="reddit",
        url="https://example.com/1",
        title="snowflake bill",
        text_excerpt="snowflake bill too expensive",
        author="x",
        posted_at=datetime.now(timezone.utc),
    )
    with_company = Signal(
        source="reddit",
        url="https://example.com/2",
        title="snowflake bill",
        text_excerpt="we at Brightloom Inc think the snowflake bill is too expensive",
        author="x",
        posted_at=datetime.now(timezone.utc),
    )
    assert score_signal(with_company) > score_signal(base)
    assert with_company.score - base.score >= config.WEIGHTS["company_detected"]
