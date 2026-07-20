"""Collection orchestration: run every collector, enrich, dedupe, and store."""

from __future__ import annotations

import logging

from . import config, db
from .classifier import classify
from .collectors import enabled_collectors
from .collectors.base import CollectorError, make_client
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


def run_collection(db_path: str) -> tuple[int, int]:
    """Collect, enrich, and store. Returns (found, newly_inserted)."""
    signals = enrich(collect_all())
    with db.connect(db_path) as conn:
        inserted = db.insert_signals(conn, signals)
    return len(signals), inserted
