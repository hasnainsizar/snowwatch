from __future__ import annotations

from datetime import datetime, timezone

import httpx

from snowwatch import classifier, db, digest
from snowwatch.collectors.jobs import StubJobSource
from snowwatch.models import STUB_SOURCE, Signal
from snowwatch.pipeline import enrich


def _seed_stubs(path: str) -> list[Signal]:
    signals = enrich(StubJobSource().fetch(httpx.Client(), []))
    with db.connect(path) as conn:
        db.insert_signals(conn, signals)
    return signals


def test_stub_signals_marked(tmp_path):
    signals = enrich(StubJobSource().fetch(httpx.Client(), []))
    assert signals
    assert all(s.source == STUB_SOURCE and s.is_stub for s in signals)


def test_stubs_excluded_by_default(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_stubs(path)
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 14)
    assert data.top_signals == []
    assert data.new_companies == []
    assert all(not s.is_stub for rows in data.by_category.values() for s in rows)
    assert data.outreach == []


def test_include_stubs_surfaces_and_tags(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_stubs(path)
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 14, include_stubs=True)
        md = digest.render_markdown(data)
        html = digest.render_html(data)
    assert any(s.is_stub for s in data.top_signals)
    assert "[STUB]" in md
    assert "STUB" in html


def test_legacy_stub_rows_migrated(tmp_path):
    path = str(tmp_path / "t.db")
    legacy = Signal(
        source="jobs",
        url="https://jobs.example.com/postings/legacy-1",
        title="Snowflake migration lead",
        text_excerpt="replatform off snowflake",
        author="Oldcorp",
        posted_at=datetime.now(timezone.utc),
    )
    with db.connect(path) as conn:
        db.insert_signals(conn, [legacy])
    with db.connect(path) as conn:
        row = conn.execute(
            "SELECT source FROM signals WHERE url LIKE '%jobs.example.com%'"
        ).fetchone()
    assert row["source"] == STUB_SOURCE


def test_headline_only_company_suppressed(tmp_path):
    path = str(tmp_path / "t.db")
    now = datetime.now(timezone.utc)
    vendor = Signal(
        source="hackernews",
        url="https://news.ycombinator.com/item?id=v1",
        title="Databricks vs Snowflake for the analytics warehouse",
        text_excerpt="Vendco Corp published a benchmark comparing the two.",
        author="poster",
        posted_at=now,
    )
    cost = Signal(
        source="hackernews",
        url="https://news.ycombinator.com/item?id=c1",
        title="Our snowflake bill is too expensive",
        text_excerpt="We at Paynco Corp are drowning in snowflake credits.",
        author="poster",
        posted_at=now,
    )
    enrich([vendor, cost])
    assert vendor.category == classifier.VENDOR_COMPARISON
    assert cost.category == classifier.COST_PAIN
    with db.connect(path) as conn:
        db.insert_signals(conn, [vendor, cost])
        data = digest.build_digest_data(conn, 14)
    joined = " ".join(data.new_companies)
    assert "Vendco" not in joined
    assert "Paynco" in joined
