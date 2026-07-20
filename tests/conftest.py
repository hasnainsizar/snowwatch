from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from snowwatch.models import Signal


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def migration_signal() -> Signal:
    return Signal(
        source="reddit",
        url="https://www.reddit.com/r/dataengineering/comments/a1/",
        title="We are migrating off Snowflake next quarter",
        text_excerpt=(
            "We at Northwind Analytics are migrating off snowflake because the "
            "snowflake bill doubled. Evaluating databricks."
        ),
        author="throwaway_de",
        posted_at=_now() - timedelta(days=1),
        engagement=42,
    )


@pytest.fixture
def cost_signal() -> Signal:
    return Signal(
        source="hackernews",
        url="https://news.ycombinator.com/item?id=111",
        title="Our Snowflake pricing is out of control",
        text_excerpt="The snowflake bill is too expensive and credits are burning fast.",
        author="hn_user",
        posted_at=_now() - timedelta(days=2),
        engagement=8,
    )


@pytest.fixture
def performance_signal() -> Signal:
    return Signal(
        source="reddit",
        url="https://www.reddit.com/r/snowflake/comments/b2/",
        title="Slow query performance on large scans",
        text_excerpt="Every slow query times out and warehouse is slow under concurrency issues.",
        author="perf_person",
        posted_at=_now() - timedelta(days=3),
    )


@pytest.fixture
def neutral_signal() -> Signal:
    return Signal(
        source="jobs",
        url="https://jobs.example.com/postings/xyz",
        title="Data Engineer role",
        text_excerpt="Work with modern data stack and dashboards.",
        author="Acme Co",
        posted_at=_now() - timedelta(days=4),
    )
