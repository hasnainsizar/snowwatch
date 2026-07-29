from __future__ import annotations

from datetime import datetime, timezone

from snowwatch import db
from snowwatch.models import Signal
from snowwatch.pipeline import enrich
from snowwatch.urls import url_hash

_ADZUNA_AD = "https://www.adzuna.com/land/ad/5787001382"


def _insert_legacy(conn, url: str, stale_hash: str, posted_at: str, terms: str) -> None:
    """Insert a row the way a pre-canonicalization build would have stored it."""
    conn.execute(
        "INSERT INTO signals (url_hash, source, url, title, text_excerpt, author, "
        "posted_at, matched_terms, score, collected_at) "
        "VALUES (?, 'jobs', ?, 'Snowflake Migration Data Architect', 'body', "
        "'Milestone', ?, ?, 57, ?)",
        (stale_hash, url, posted_at, terms, posted_at),
    )


def test_dedupe_by_url(tmp_path, cost_signal):
    path = str(tmp_path / "t.db")
    enrich([cost_signal])
    with db.connect(path) as conn:
        first = db.insert_signals(conn, [cost_signal])
        second = db.insert_signals(conn, [cost_signal])
    assert first == 1
    assert second == 0


def test_dedupe_ignores_case_and_whitespace(tmp_path, cost_signal):
    path = str(tmp_path / "t.db")
    dup = type(cost_signal)(
        source=cost_signal.source,
        url="  " + cost_signal.url.upper() + " ",
        title=cost_signal.title,
        text_excerpt=cost_signal.text_excerpt,
        author=cost_signal.author,
        posted_at=cost_signal.posted_at,
    )
    enrich([cost_signal, dup])
    with db.connect(path) as conn:
        inserted = db.insert_signals(conn, [cost_signal, dup])
    assert inserted == 1


def test_signals_since_orders_by_score(tmp_path, migration_signal, cost_signal, neutral_signal):
    path = str(tmp_path / "t.db")
    enrich([migration_signal, cost_signal, neutral_signal])
    with db.connect(path) as conn:
        db.insert_signals(conn, [migration_signal, cost_signal, neutral_signal])
        rows = db.signals_since(conn, 7)
    scores = [r.score for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_dedupe_ignores_tracking_params(tmp_path, cost_signal):
    path = str(tmp_path / "t.db")
    tracked = type(cost_signal)(
        source=cost_signal.source,
        url=cost_signal.url + "&utm_source=api&se=Ag5RgtaH",
        title=cost_signal.title,
        text_excerpt=cost_signal.text_excerpt,
        author=cost_signal.author,
        posted_at=cost_signal.posted_at,
    )
    enrich([cost_signal, tracked])
    with db.connect(path) as conn:
        inserted = db.insert_signals(conn, [cost_signal, tracked])
    assert inserted == 1


def _seed_legacy_duplicates(path: str) -> None:
    """Three collections of one Adzuna ad, each stored under its own stale key."""
    with db.connect(path) as conn:
        for i, token in enumerate(["AgWOyKeE", "fua3a82E", "xHrE9C-F"]):
            _insert_legacy(
                conn,
                f"{_ADZUNA_AD}?se={token}&utm_medium=api&v=439E69FF",
                f"legacy-hash-{i}",
                f"2026-07-0{i + 3}T13:21:31+00:00",
                f"term-{i}",
            )
        conn.execute("PRAGMA user_version = 0")


def test_canonical_migration_merges_duplicates(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_legacy_duplicates(path)
    with db.connect(path) as conn:
        rows = conn.execute("SELECT * FROM signals").fetchall()
    assert len(rows) == 1


def test_canonical_migration_keeps_earliest_and_unions_terms(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_legacy_duplicates(path)
    with db.connect(path) as conn:
        row = conn.execute("SELECT * FROM signals").fetchone()
    assert row["posted_at"] == "2026-07-03T13:21:31+00:00"
    assert sorted(row["matched_terms"].split("\x1f")) == ["term-0", "term-1", "term-2"]


def test_canonical_migration_rewrites_stale_hashes(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_legacy_duplicates(path)
    with db.connect(path) as conn:
        row = conn.execute("SELECT url_hash FROM signals").fetchone()
    assert row["url_hash"] == url_hash(_ADZUNA_AD)


def test_canonical_migration_is_idempotent(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_legacy_duplicates(path)
    with db.connect(path) as conn:
        first = db.recanonicalize(conn)
    with db.connect(path) as conn:
        second = db.recanonicalize(conn)
        remaining = db.total_count(conn)
    assert first == 0  # the migration on connect already merged the group
    assert second == 0
    assert remaining == 1


def test_migrated_rows_block_recollection_of_the_same_ad(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_legacy_duplicates(path)
    fresh = Signal(
        source="jobs",
        url=f"{_ADZUNA_AD}?se=BrandNewToken&utm_medium=api&v=439E69FF",
        title="Snowflake Migration Data Architect",
        text_excerpt="body",
        author="Milestone",
        posted_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    with db.connect(path) as conn:
        inserted = db.insert_signals(conn, [fresh])
        remaining = db.total_count(conn)
    assert inserted == 0
    assert remaining == 1


def test_counts_by_source(tmp_path, migration_signal, cost_signal):
    path = str(tmp_path / "t.db")
    enrich([migration_signal, cost_signal])
    with db.connect(path) as conn:
        db.insert_signals(conn, [migration_signal, cost_signal])
        counts = dict(db.counts_by(conn, "source"))
    assert counts["reddit"] == 1
    assert counts["hackernews"] == 1
