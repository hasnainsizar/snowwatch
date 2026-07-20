"""SQLite persistence. Single file, no external services.

Dedupe is enforced at the schema level via a UNIQUE url_hash column; inserts use
INSERT OR IGNORE so re-collecting the same signal is a no-op.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .models import Signal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash      TEXT NOT NULL UNIQUE,
    source        TEXT NOT NULL,
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    text_excerpt  TEXT NOT NULL,
    author        TEXT NOT NULL,
    posted_at     TEXT NOT NULL,
    matched_terms TEXT NOT NULL,
    company       TEXT,
    category      TEXT,
    score         INTEGER NOT NULL DEFAULT 0,
    engagement    INTEGER NOT NULL DEFAULT 0,
    collected_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_posted_at ON signals(posted_at);
CREATE INDEX IF NOT EXISTS idx_signals_category ON signals(category);
"""


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    """Yield a configured connection with the schema applied."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _to_iso(value: datetime) -> str:
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _row_to_signal(row: sqlite3.Row) -> Signal:
    terms = [t for t in row["matched_terms"].split("\x1f") if t]
    return Signal(
        source=row["source"],
        url=row["url"],
        title=row["title"],
        text_excerpt=row["text_excerpt"],
        author=row["author"],
        posted_at=datetime.fromisoformat(row["posted_at"]),
        matched_terms=terms,
        company=row["company"],
        category=row["category"],
        score=row["score"],
        engagement=row["engagement"],
    )


def insert_signals(conn: sqlite3.Connection, signals: Iterable[Signal]) -> int:
    """Insert signals, skipping URL-hash duplicates. Returns count newly stored."""
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for sig in signals:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO signals (
                url_hash, source, url, title, text_excerpt, author, posted_at,
                matched_terms, company, category, score, engagement, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sig.url_hash,
                sig.source,
                sig.url,
                sig.title,
                sig.text_excerpt,
                sig.author,
                _to_iso(sig.posted_at),
                "\x1f".join(sig.matched_terms),
                sig.company,
                sig.category,
                sig.score,
                sig.engagement,
                now,
            ),
        )
        inserted += cur.rowcount
    return inserted


def signals_since(conn: sqlite3.Connection, days: int) -> list[Signal]:
    """Return signals posted within the trailing window, highest score first."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT * FROM signals WHERE posted_at >= ? ORDER BY score DESC, posted_at DESC",
        (cutoff,),
    ).fetchall()
    return [_row_to_signal(r) for r in rows]


def known_companies_before(conn: sqlite3.Connection, days: int) -> set[str]:
    """Companies first seen before the trailing window (for new-company diffing)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT DISTINCT company FROM signals WHERE company IS NOT NULL AND posted_at < ?",
        (cutoff,),
    ).fetchall()
    return {r["company"] for r in rows if r["company"]}


def counts_by(conn: sqlite3.Connection, column: str) -> list[tuple[str, int]]:
    """Grouped counts for a whitelisted column, most frequent first."""
    if column not in {"source", "category"}:
        raise ValueError(f"unsupported group column: {column}")
    rows = conn.execute(
        f"SELECT COALESCE({column}, 'UNKNOWN') AS k, COUNT(*) AS n "
        f"FROM signals GROUP BY k ORDER BY n DESC"
    ).fetchall()
    return [(r["k"], r["n"]) for r in rows]


def source_summary(conn: sqlite3.Connection) -> list[tuple[str, int, str | None]]:
    """Per-source (source, count, last_collected_at), most signals first."""
    rows = conn.execute(
        "SELECT source, COUNT(*) AS n, MAX(collected_at) AS last "
        "FROM signals GROUP BY source ORDER BY n DESC"
    ).fetchall()
    return [(r["source"], r["n"], r["last"]) for r in rows]


def counts_by_week(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Signal counts grouped by ISO year-week of posting, newest first."""
    rows = conn.execute(
        "SELECT strftime('%Y-W%W', posted_at) AS wk, COUNT(*) AS n "
        "FROM signals GROUP BY wk ORDER BY wk DESC"
    ).fetchall()
    return [(r["wk"], r["n"]) for r in rows]


def count_posted_between(conn: sqlite3.Connection, start_days_ago: int, end_days_ago: int) -> int:
    """Count signals posted in the window [now-start, now-end), start > end."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=start_days_ago)).isoformat()
    end = (now - timedelta(days=end_days_ago)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM signals WHERE posted_at >= ? AND posted_at < ?",
        (start, end),
    ).fetchone()
    return int(row["n"])


def total_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM signals").fetchone()["n"])
