"""SQLite persistence. Single file, no external services.

Dedupe is enforced at the schema level via a UNIQUE url_hash column; inserts use
INSERT OR IGNORE so re-collecting the same signal is a no-op.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .models import STUB_SOURCE, Signal
from .urls import STUB_URL_HOST, url_hash

logger = logging.getLogger("snowwatch")

# Bumped when a stored-data migration must run once against existing databases.
# 1: url_hash recomputed from the canonical URL, duplicate rows merged.
# 2: stub URLs moved to their own canonical namespace.
_SCHEMA_VERSION = 2

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
    staffing_flag INTEGER NOT NULL DEFAULT 0,
    collected_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_posted_at ON signals(posted_at);
CREATE INDEX IF NOT EXISTS idx_signals_category ON signals(category);
"""


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    """Yield a configured connection with the schema applied and migrations run."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply idempotent schema/data migrations to a pre-existing database."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(signals)")}
    if "staffing_flag" not in columns:
        conn.execute("ALTER TABLE signals ADD COLUMN staffing_flag INTEGER NOT NULL DEFAULT 0")
    # Restores the stub tag on rows stored before the stub source had its own
    # name, and keeps it attached to any stub row a later migration touches.
    conn.execute(
        "UPDATE signals SET source = ? WHERE source != ? AND url LIKE ?",
        (STUB_SOURCE, STUB_SOURCE, f"%{STUB_URL_HOST}%"),
    )
    if conn.execute("PRAGMA user_version").fetchone()[0] < _SCHEMA_VERSION:
        merged = recanonicalize(conn)
        if merged:
            logger.info("canonical dedupe: merged %d duplicate rows", merged)
        conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


def _merge_terms(rows: list[sqlite3.Row]) -> str:
    """Union of every duplicate's matched terms, in stable order."""
    terms = {t for row in rows for t in row["matched_terms"].split("\x1f") if t}
    return "\x1f".join(sorted(terms))


def recanonicalize(conn: sqlite3.Connection) -> int:
    """Rewrite url_hash from the canonical URL and merge duplicate rows.

    Rows whose URLs share a canonical form collapse into the earliest-posted
    one, which inherits the union of the group's matched terms. Returns the
    number of rows removed. Safe to re-run: a database with no duplicates left
    is rewritten to the same values and reports zero.
    """
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in conn.execute("SELECT * FROM signals").fetchall():
        groups.setdefault(url_hash(row["url"]), []).append(row)

    # Delete every loser before rewriting keepers, so no update can collide with
    # a hash still held by a row on its way out.
    keepers: list[tuple[str, str, int]] = []
    merged = 0
    for canonical, rows in groups.items():
        keeper = min(rows, key=lambda r: r["posted_at"])
        losers = [r["id"] for r in rows if r["id"] != keeper["id"]]
        if losers:
            conn.executemany("DELETE FROM signals WHERE id = ?", [(i,) for i in losers])
            merged += len(losers)
        keepers.append((canonical, _merge_terms(rows), keeper["id"]))

    conn.executemany(
        "UPDATE signals SET url_hash = ?, matched_terms = ? WHERE id = ?", keepers
    )
    return merged


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
        staffing_flag=bool(row["staffing_flag"]),
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
                matched_terms, company, category, score, engagement, staffing_flag,
                collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                int(sig.staffing_flag),
                now,
            ),
        )
        inserted += cur.rowcount
    return inserted


def all_signals(conn: sqlite3.Connection) -> list[tuple[int, Signal]]:
    """Every stored signal paired with its row id, for re-enrichment."""
    rows = conn.execute("SELECT * FROM signals").fetchall()
    return [(row["id"], _row_to_signal(row)) for row in rows]


def update_enrichment(conn: sqlite3.Connection, rows: Iterable[tuple[int, Signal]]) -> None:
    """Write recomputed score, category, company, terms, and staffing flag."""
    conn.executemany(
        "UPDATE signals SET score = ?, category = ?, company = ?, matched_terms = ?, "
        "staffing_flag = ? WHERE id = ?",
        [
            (
                sig.score,
                sig.category,
                sig.company,
                "\x1f".join(sig.matched_terms),
                int(sig.staffing_flag),
                row_id,
            )
            for row_id, sig in rows
        ],
    )


def signals_since(conn: sqlite3.Connection, days: int, include_stubs: bool = True) -> list[Signal]:
    """Return signals posted within the trailing window, highest score first."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    stub_clause = "" if include_stubs else " AND source != ?"
    params: tuple = (cutoff,) if include_stubs else (cutoff, STUB_SOURCE)
    rows = conn.execute(
        f"SELECT * FROM signals WHERE posted_at >= ?{stub_clause} "
        "ORDER BY score DESC, posted_at DESC",
        params,
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


def count_posted_between(
    conn: sqlite3.Connection, start_days_ago: int, end_days_ago: int, include_stubs: bool = True
) -> int:
    """Count signals posted in the window [now-start, now-end), start > end."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=start_days_ago)).isoformat()
    end = (now - timedelta(days=end_days_ago)).isoformat()
    stub_clause = "" if include_stubs else " AND source != ?"
    params: tuple = (start, end) if include_stubs else (start, end, STUB_SOURCE)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM signals WHERE posted_at >= ? AND posted_at < ?{stub_clause}",
        params,
    ).fetchone()
    return int(row["n"])


def total_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM signals").fetchone()["n"])
