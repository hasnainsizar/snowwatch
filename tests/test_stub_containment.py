from __future__ import annotations

from datetime import datetime, timezone

import httpx

from snowwatch import classifier, db, digest, pipeline
from snowwatch.collectors.jobs import StubJobSource
from snowwatch.models import STUB_SOURCE, Signal
from snowwatch.pipeline import enrich
from snowwatch.urls import STUB_URL_HOST


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


def test_migration_preserves_the_stub_tag(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_stubs(path)
    with db.connect(path) as conn:
        conn.execute("PRAGMA user_version = 0")
    with db.connect(path) as conn:
        rows = conn.execute(
            "SELECT source FROM signals WHERE url LIKE ?", (f"%{STUB_URL_HOST}%",)
        ).fetchall()
    assert len(rows) == 2
    assert all(r["source"] == STUB_SOURCE for r in rows)


def test_migration_keeps_stubs_separate_from_real_jobs(tmp_path):
    path = str(tmp_path / "t.db")
    real = Signal(
        source="jobs",
        url="https://www.adzuna.com/land/ad/5787001382?se=tok&utm_medium=api",
        title="Snowflake Migration Data Architect",
        text_excerpt="replatform off snowflake",
        author="Milestone",
        posted_at=datetime.now(timezone.utc),
    )
    enrich([real])
    _seed_stubs(path)
    with db.connect(path) as conn:
        db.insert_signals(conn, [real])
        conn.execute("PRAGMA user_version = 0")
    with db.connect(path) as conn:
        counts = dict(db.counts_by(conn, "source"))
        total = db.total_count(conn)
    assert counts[STUB_SOURCE] == 2
    assert counts["jobs"] == 1
    assert total == 3


def test_seed_stubs_is_idempotent(tmp_path):
    path = str(tmp_path / "t.db")
    first_found, first_new = pipeline.seed_stubs(path)
    second_found, second_new = pipeline.seed_stubs(path)
    with db.connect(path) as conn:
        total = db.total_count(conn)
    assert (first_found, first_new) == (2, 2)
    assert (second_found, second_new) == (2, 0)
    assert total == 2


def test_seeded_stubs_are_in_window_and_tagged(tmp_path):
    path = str(tmp_path / "t.db")
    pipeline.seed_stubs(path)
    with db.connect(path) as conn:
        rows = db.signals_since(conn, 30)
    assert len(rows) == 2
    assert all(s.source == STUB_SOURCE for s in rows)


def test_seeded_stubs_render_stub_cards_with_outreach(tmp_path):
    path = str(tmp_path / "t.db")
    pipeline.seed_stubs(path)
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 30, include_stubs=True)
        md = digest.render_markdown(data)
    assert md.count("[STUB]") >= 1
    assert len(data.top_signals) == 2
    assert len(data.outreach) == 2


def test_stub_digest_written_to_a_separate_file(tmp_path):
    path = str(tmp_path / "t.db")
    out = str(tmp_path / "digests")
    pipeline.seed_stubs(path)
    with db.connect(path) as conn:
        plain_md, plain_html = digest.write_digest(conn, 30, out)
        stub_md, stub_html = digest.write_digest(conn, 30, out, include_stubs=True)
    assert stub_md.name.endswith("-stubs.md")
    assert stub_html.name.endswith("-stubs.html")
    assert {plain_md, plain_html}.isdisjoint({stub_md, stub_html})
    assert "[STUB]" in stub_md.read_text(encoding="utf-8")
    assert "[STUB]" not in plain_md.read_text(encoding="utf-8")


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
