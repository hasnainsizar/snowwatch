"""Job-posting collector with a pluggable source interface.

Public job APIs generally require credentials. Rather than hard-code one, the
collector delegates to a ``JobSource``. The default ``StubJobSource`` returns a
small offline sample so the pipeline runs end to end with no keys. To use real
data, set the ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables and the
collector switches to :class:`AdzunaJobSource` automatically.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx

from .. import config
from ..models import Signal
from .base import CollectorError, polite_get, truncate


class JobSource(Protocol):
    """Supplies raw job postings already normalized into Signals."""

    def fetch(self, client: httpx.Client, terms: list[str]) -> list[Signal]:
        ...


class StubJobSource:
    """Offline sample source. Keeps the pipeline runnable without API keys."""

    def fetch(self, client: httpx.Client, terms: list[str]) -> list[Signal]:
        now = datetime.now(timezone.utc)
        samples = [
            {
                "id": "stub-1",
                "title": "Senior Data Engineer — Snowflake Migration",
                "company": "Northwind Analytics",
                "description": (
                    "We are replatforming off Snowflake to reduce compute cost. "
                    "Lead the Snowflake migration to a lakehouse and own cost "
                    "optimization across the pipeline."
                ),
                "age_days": 2,
            },
            {
                "id": "stub-2",
                "title": "Analytics Engineer (Cost Optimization Snowflake)",
                "company": "Brightloom Inc",
                "description": (
                    "Our Snowflake bill is growing fast. Drive cost optimization "
                    "and evaluate Databricks as an alternative warehouse."
                ),
                "age_days": 5,
            },
        ]
        signals: list[Signal] = []
        for s in samples:
            posted = now - timedelta(days=int(s["age_days"]))
            signals.append(
                Signal(
                    source="jobs",
                    url=f"https://jobs.example.com/postings/{s['id']}",
                    title=truncate(str(s["title"]), 200),
                    text_excerpt=truncate(str(s["description"])),
                    author=str(s["company"]),
                    posted_at=posted,
                    company=str(s["company"]),
                )
            )
        return signals


class AdzunaJobSource:
    """Adzuna Jobs API source, active when app id/key env vars are present."""

    _API = "https://api.adzuna.com/v1/api/jobs/us/search/1"

    def __init__(self, app_id: str, app_key: str) -> None:
        self._app_id = app_id
        self._app_key = app_key

    def fetch(self, client: httpx.Client, terms: list[str]) -> list[Signal]:
        signals: list[Signal] = []
        seen: set[str] = set()
        for term in terms:
            resp = polite_get(
                client,
                self._API,
                params={
                    "app_id": self._app_id,
                    "app_key": self._app_key,
                    "what": term,
                    "results_per_page": 25,
                    "content-type": "application/json",
                },
            )
            for item in resp.json().get("results", []):
                sig = self._to_signal(item)
                if sig is None or sig.url in seen:
                    continue
                seen.add(sig.url)
                signals.append(sig)
        return signals

    @staticmethod
    def _to_signal(item: dict) -> Signal | None:
        url = item.get("redirect_url")
        if not url:
            return None
        company = (item.get("company") or {}).get("display_name")
        created = item.get("created")
        try:
            posted = (
                datetime.fromisoformat(created.replace("Z", "+00:00"))
                if created
                else datetime.now(timezone.utc)
            )
        except ValueError:
            posted = datetime.now(timezone.utc)
        return Signal(
            source="jobs",
            url=url,
            title=truncate(item.get("title") or "(job posting)", 200),
            text_excerpt=truncate(item.get("description") or ""),
            author=company or "unknown",
            posted_at=posted,
            company=company,
        )


def default_job_source() -> JobSource:
    """Pick a live source when credentials exist, else the offline stub."""
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if app_id and app_key:
        return AdzunaJobSource(app_id, app_key)
    return StubJobSource()


class JobsCollector:
    name = "jobs"

    def __init__(self, source: JobSource | None = None) -> None:
        self._source = source or default_job_source()

    def collect(self, client: httpx.Client) -> list[Signal]:
        try:
            return self._source.fetch(client, config.JOB_QUERY_TERMS)
        except CollectorError:
            raise
        except Exception as exc:  # noqa: BLE001 - source-agnostic boundary
            raise CollectorError(f"job source failed: {exc}") from exc
