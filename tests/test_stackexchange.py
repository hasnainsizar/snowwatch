from __future__ import annotations

import httpx
import pytest

from snowwatch import config, db
from snowwatch.collectors.stackexchange import StackExchangeCollector, strip_html
from snowwatch.pipeline import enrich


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s=0: sleeps.append(s))
    return sleeps


@pytest.fixture(autouse=True)
def _single_site_term(monkeypatch):
    monkeypatch.setattr(config, "STACKEXCHANGE_SITES", ["stackoverflow"])
    monkeypatch.setattr(config, "STACKEXCHANGE_QUERY_TERMS", ["snowflake cost"])


def _item(**over) -> dict:
    item = {
        "title": "Why is our <b>Snowflake</b> cost so high?",
        "link": "https://stackoverflow.com/q/1",
        "creation_date": 1_700_000_000,
        "owner": {"display_name": "dataperson"},
        "body": "<p>Our snowflake bill is <em>too expensive</em> &amp; growing.</p>",
        "score": 4,
        "answer_count": 2,
    }
    item.update(over)
    return item


def _mock_client(payload_for) -> tuple[httpx.Client, list[str]]:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        term = request.url.params.get("q", "")
        calls.append(term)
        return httpx.Response(200, json=payload_for(term))

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_strip_html():
    assert strip_html("<p>Hello <b>world</b> &amp; more</p>") == "Hello world & more"
    assert strip_html("") == ""


def test_normalization():
    client, _ = _mock_client(lambda term: {"items": [_item()], "quota_remaining": 9000})
    signals = StackExchangeCollector().collect(client)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.source == "stackexchange"
    assert sig.url == "https://stackoverflow.com/q/1"
    assert sig.author == "dataperson"
    assert "<" not in sig.text_excerpt and "&amp;" not in sig.text_excerpt
    assert "too expensive" in sig.text_excerpt
    assert sig.matched_terms == ["snowflake cost"]
    assert sig.posted_at.year == 2023


def test_missing_owner_defaults_author():
    client, _ = _mock_client(lambda term: {"items": [_item(owner=None)], "quota_remaining": 9000})
    signals = StackExchangeCollector().collect(client)
    assert signals[0].author == "unknown"


def test_within_run_dedupe():
    dup = {"items": [_item(), _item()], "quota_remaining": 9000}
    client, _ = _mock_client(lambda term: dup)
    signals = StackExchangeCollector().collect(client)
    assert len(signals) == 1


def test_backoff_respected(_no_sleep):
    client, _ = _mock_client(lambda term: {"items": [_item()], "backoff": 3, "quota_remaining": 9000})
    StackExchangeCollector().collect(client)
    assert 3.0 in _no_sleep


def test_quota_stop(monkeypatch):
    monkeypatch.setattr(config, "STACKEXCHANGE_QUERY_TERMS", ["snowflake cost", "snowflake slow"])
    client, calls = _mock_client(
        lambda term: {"items": [_item()], "quota_remaining": config.STACKEXCHANGE_QUOTA_FLOOR}
    )
    StackExchangeCollector().collect(client)
    assert calls == ["snowflake cost"]


def test_key_passed_when_present(monkeypatch):
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("key"))
        return httpx.Response(200, json={"items": [], "quota_remaining": 9000})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    StackExchangeCollector(key="abc123").collect(client)
    assert seen == ["abc123"]


def test_dedupe_against_existing_signals(tmp_path):
    client, _ = _mock_client(lambda term: {"items": [_item()], "quota_remaining": 9000})
    signals = enrich(StackExchangeCollector().collect(client))
    path = str(tmp_path / "t.db")
    with db.connect(path) as conn:
        first = db.insert_signals(conn, signals)
        second = db.insert_signals(conn, signals)
    assert first == 1
    assert second == 0
