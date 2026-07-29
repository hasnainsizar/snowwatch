"""Normalized data types shared across collectors, scoring, and storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .urls import url_hash

# Source tag for offline stub job signals, kept distinct so digests can exclude
# them by default.
STUB_SOURCE = "jobs-stub"


@dataclass(slots=True)
class Signal:
    """A single normalized displacement signal from any source."""

    source: str
    url: str
    title: str
    text_excerpt: str
    author: str
    posted_at: datetime
    matched_terms: list[str] = field(default_factory=list)
    company: str | None = None
    category: str | None = None
    score: int = 0
    engagement: int = 0
    staffing_flag: bool = False

    @property
    def url_hash(self) -> str:
        """Stable dedupe key derived from the canonical URL."""
        return url_hash(self.url)

    @property
    def is_stub(self) -> bool:
        """True for offline stub job signals."""
        return self.source == STUB_SOURCE

    @property
    def content(self) -> str:
        """Combined lowercase text used by scoring and classification."""
        return f"{self.title}\n{self.text_excerpt}".lower()
