"""Signal collectors. One module per source, each exposing a ``collect``."""

from __future__ import annotations

from .base import Collector, CollectorError
from .hackernews import HackerNewsCollector
from .jobs import JobsCollector, JobSource, StubJobSource
from .reddit import RedditCollector

ALL_COLLECTORS: list[type[Collector]] = [
    HackerNewsCollector,
    RedditCollector,
    JobsCollector,
]

__all__ = [
    "Collector",
    "CollectorError",
    "HackerNewsCollector",
    "RedditCollector",
    "JobsCollector",
    "JobSource",
    "StubJobSource",
    "ALL_COLLECTORS",
]
