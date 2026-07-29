"""Collection orchestration: run every collector, enrich, dedupe, and store."""

from __future__ import annotations

import logging

from . import config, db
from .classifier import classify
from .collectors import enabled_collectors
from .collectors.base import CollectorError, make_client
from .collectors.jobs import StubJobSource
from .models import Signal
from .scoring import score_signal

logger = logging.getLogger("snowwatch")


def enrich(signals: list[Signal]) -> list[Signal]:
    """Score and classify each signal in place."""
    for sig in signals:
        score_signal(sig)
        classify(sig)
    return signals


def collect_all() -> list[Signal]:
    """Run the enabled collectors. A failing source is logged and skipped."""
    if not config.reddit_enabled():
        logger.info("reddit: disabled (requires approved Reddit Data API access)")

    collected: list[Signal] = []
    with make_client() as client:
        for collector in enabled_collectors():
            try:
                found = collector.collect(client)
                logger.info("%s: %d signals", collector.name, len(found))
                collected.extend(found)
            except CollectorError as exc:
                logger.warning("%s failed, skipping: %s", collector.name, exc)
            except Exception as exc:  # noqa: BLE001 - keep other sources alive
                logger.warning("%s raised unexpectedly, skipping: %s", collector.name, exc)
    return collected


def seed_stubs(db_path: str) -> tuple[int, int]:
    """Store the offline demonstration stub signals. Returns (found, newly stored).

    Idempotent: the stubs carry fixed URLs, so a second run dedupes against the
    rows already stored and inserts nothing. Useful when live credentials are
    configured, because the jobs collector then never emits stubs on its own.
    """
    with make_client() as client:
        signals = enrich(StubJobSource().fetch(client, config.JOB_QUERY_TERMS))
    with db.connect(db_path) as conn:
        inserted = db.insert_signals(conn, signals)
    return len(signals), inserted


def rescore_stored(db_path: str) -> int:
    """Re-apply the current scoring and classification rules to stored signals.

    Score and category are written at collection time and read back verbatim by
    the digest, so a change to the scoring or direction rules only reaches past
    signals through this pass. Matched terms are recomputed from the text;
    collector-supplied company names are kept. Returns the number of rows whose
    score or category changed.
    """
    with db.connect(db_path) as conn:
        stored = db.all_signals(conn)
        changed = 0
        for _row_id, sig in stored:
            before = (sig.score, sig.category)
            sig.matched_terms = []
            score_signal(sig)
            classify(sig)
            if (sig.score, sig.category) != before:
                changed += 1
        db.update_enrichment(conn, stored)
    return changed


def run_collection(db_path: str) -> tuple[int, int]:
    """Collect, enrich, and store. Returns (found, newly_inserted)."""
    signals = enrich(collect_all())
    with db.connect(db_path) as conn:
        inserted = db.insert_signals(conn, signals)
    return len(signals), inserted
