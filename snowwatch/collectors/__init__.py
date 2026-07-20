"""Signal collectors. One module per source, each exposing a ``collect``."""

from __future__ import annotations

from .. import config
from .base import Collector, CollectorError
from .hackernews import HackerNewsCollector
from .jobs import JobsCollector, JobSource, StubJobSource
from .reddit import RedditCollector
from .stackexchange import StackExchangeCollector

COLLECTOR_REGISTRY: dict[str, type[Collector]] = {
    "hackernews": HackerNewsCollector,
    "stackexchange": StackExchangeCollector,
    "jobs": JobsCollector,
    "reddit": RedditCollector,
}


def enabled_collectors() -> list[Collector]:
    """Instantiate the configured collectors, honoring the reddit gate."""
    names = list(config.ENABLED_COLLECTORS)
    if config.reddit_enabled() and "reddit" not in names:
        names.append("reddit")
    return [COLLECTOR_REGISTRY[n]() for n in names if n in COLLECTOR_REGISTRY]


__all__ = [
    "Collector",
    "CollectorError",
    "HackerNewsCollector",
    "StackExchangeCollector",
    "RedditCollector",
    "JobsCollector",
    "JobSource",
    "StubJobSource",
    "COLLECTOR_REGISTRY",
    "enabled_collectors",
]
