from __future__ import annotations

import logging

import httpx
import pytest

from snowwatch import config, pipeline
from snowwatch.collectors import RedditCollector, enabled_collectors
from snowwatch.collectors.base import CollectorError


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s=0: None)


@pytest.fixture(autouse=True)
def _single_scope(monkeypatch):
    monkeypatch.setattr(config, "SUBREDDITS", ["dataengineering"])
    monkeypatch.setattr(config, "QUERY_TERMS", ["snowflake bill"])


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SNOWWATCH_ENABLE_REDDIT", raising=False)
    monkeypatch.setattr(config, "ENABLED_COLLECTORS", ["hackernews", "stackexchange", "jobs"])
    assert config.reddit_enabled() is False
    names = {type(c).__name__ for c in enabled_collectors()}
    assert "RedditCollector" not in names


def test_enabled_via_env_flag(monkeypatch):
    monkeypatch.setenv("SNOWWATCH_ENABLE_REDDIT", "1")
    monkeypatch.setattr(config, "ENABLED_COLLECTORS", ["hackernews", "stackexchange", "jobs"])
    assert config.reddit_enabled() is True
    names = {type(c).__name__ for c in enabled_collectors()}
    assert "RedditCollector" in names


def test_enabled_via_config(monkeypatch):
    monkeypatch.delenv("SNOWWATCH_ENABLE_REDDIT", raising=False)
    monkeypatch.setattr(config, "ENABLED_COLLECTORS", ["hackernews", "reddit"])
    assert config.reddit_enabled() is True


def test_disabled_line_logged_once(monkeypatch, caplog):
    monkeypatch.delenv("SNOWWATCH_ENABLE_REDDIT", raising=False)
    monkeypatch.setattr(config, "ENABLED_COLLECTORS", [])
    with caplog.at_level(logging.INFO, logger="snowwatch"):
        pipeline.collect_all()
    disabled = [r for r in caplog.records if "reddit: disabled" in r.message]
    assert len(disabled) == 1


def test_enabled_without_credentials_errors():
    collector = RedditCollector(client_id=None, client_secret=None)
    with pytest.raises(CollectorError):
        collector.collect(httpx.Client())


def test_oauth_flow_collects(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(
            200,
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "permalink": "/r/dataengineering/comments/x/",
                                "title": "Our snowflake bill is out of control",
                                "selftext": "leaving snowflake soon",
                                "created_utc": 1_700_000_000,
                                "author": "de_person",
                                "score": 12,
                                "num_comments": 5,
                            }
                        }
                    ]
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    collector = RedditCollector(client_id="id", client_secret="secret")
    signals = collector.collect(client)
    assert len(signals) == 1
    assert signals[0].source == "reddit"
    assert signals[0].url == "https://www.reddit.com/r/dataengineering/comments/x/"


def test_no_public_fallback_method():
    assert not hasattr(RedditCollector, "_public_search")
