from __future__ import annotations

from snowwatch import db
from snowwatch.pipeline import enrich


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


def test_counts_by_source(tmp_path, migration_signal, cost_signal):
    path = str(tmp_path / "t.db")
    enrich([migration_signal, cost_signal])
    with db.connect(path) as conn:
        db.insert_signals(conn, [migration_signal, cost_signal])
        counts = dict(db.counts_by(conn, "source"))
    assert counts["reddit"] == 1
    assert counts["hackernews"] == 1
