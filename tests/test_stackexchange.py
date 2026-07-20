from __future__ import annotations

import httpx
import pytest

from snowwatch import classifier, config, db
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


def test_recency_query_params(monkeypatch):
    from datetime import datetime, timezone

    captured: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(dict(request.url.params))
        return httpx.Response(200, json={"items": [], "quota_remaining": 9000})

    monkeypatch.setattr(config, "STACKEXCHANGE_FROMDATE_DAYS", 30)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    StackExchangeCollector().collect(client)

    params = captured[0]
    assert params["sort"] == "creation"
    assert params["order"] == "desc"
    floor = int((datetime.now(timezone.utc).timestamp())) - 31 * 86400
    ceil = int((datetime.now(timezone.utc).timestamp())) - 29 * 86400
    assert floor <= int(params["fromdate"]) <= ceil


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


def test_matched_terms_union_on_dedupe(monkeypatch):
    monkeypatch.setattr(config, "STACKEXCHANGE_QUERY_TERMS", ["snowflake cost", "snowflake"])
    client, _ = _mock_client(lambda term: {"items": [_item()], "quota_remaining": 9000})
    signals = StackExchangeCollector().collect(client)
    assert len(signals) == 1
    assert signals[0].matched_terms == ["snowflake cost", "snowflake"]


def test_bare_term_true_warehouse_scores(monkeypatch):
    monkeypatch.setattr(config, "STACKEXCHANGE_QUERY_TERMS", ["snowflake"])
    warehouse = _item(
        title="Snowflake warehouse query is slow",
        body="<p>My snowflake virtual warehouse runs a slow query that times out on a large table.</p>",
        link="https://stackoverflow.com/q/wh",
    )
    client, _ = _mock_client(lambda term: {"items": [warehouse], "quota_remaining": 9000})
    signals = enrich(StackExchangeCollector().collect(client))
    assert signals[0].matched_terms == ["snowflake"]
    assert signals[0].category == classifier.PERFORMANCE_COMPLAINT


def test_bare_term_weather_false_match_is_other(monkeypatch):
    monkeypatch.setattr(config, "STACKEXCHANGE_QUERY_TERMS", ["snowflake"])
    weather = _item(
        title="How to animate a snowflake falling in CSS",
        body="<p>I want snowflakes drifting down a winter holiday page. The animation is frustrated by jitter.</p>",
        link="https://stackoverflow.com/q/snow",
    )
    client, _ = _mock_client(lambda term: {"items": [weather], "quota_remaining": 9000})
    signals = enrich(StackExchangeCollector().collect(client))
    assert signals[0].category == classifier.OTHER


def test_bare_term_cdp_false_match_is_other(monkeypatch):
    monkeypatch.setattr(config, "STACKEXCHANGE_QUERY_TERMS", ["snowflake"])
    cdp = _item(
        title="Snowflake CDP audience not syncing",
        body="<p>Our Snowflake customer data platform audience will not sync to the marketing destination.</p>",
        link="https://stackoverflow.com/q/cdp",
    )
    client, _ = _mock_client(lambda term: {"items": [cdp], "quota_remaining": 9000})
    signals = enrich(StackExchangeCollector().collect(client))
    assert signals[0].category == classifier.OTHER
