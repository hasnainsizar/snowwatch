"""Collection orchestration: run every collector, enrich, dedupe, and store."""

from __future__ import annotations

import logging

from . import db
from .classifier import classify
from .collectors import ALL_COLLECTORS
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
    """Run all collectors. A failing source is logged and skipped."""
    collected: list[Signal] = []
    with make_client() as client:
        for collector_cls in ALL_COLLECTORS:
            collector = collector_cls()
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
