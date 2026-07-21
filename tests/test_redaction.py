from __future__ import annotations

import logging

import httpx
import pytest

from snowwatch.collectors.base import CollectorError, polite_get
from snowwatch.logutil import RedactingFilter, configure_logging, redact, request_line

_KEY = "b74298708a9dd0ddf69af1dbc6f51e91"
_ID = "a1b2c3d4"
_ADZUNA = f"https://api.adzuna.com/v1/api/jobs/us/search/1?app_id={_ID}&app_key={_KEY}&what=snowflake"


def test_redact_masks_credentials():
    out = redact(_ADZUNA)
    assert _ID not in out
    assert _KEY not in out
    assert "app_id=***" in out
    assert "app_key=***" in out
    assert "what=snowflake" in out


def test_redact_generic_secrets():
    out = redact("token=abc123&client_secret=zzz&key=qqq&normal=ok")
    assert "abc123" not in out and "zzz" not in out and "qqq" not in out
    assert "token=***" in out and "client_secret=***" in out and "key=***" in out
    assert "normal=ok" in out


def test_redact_leaves_plain_text_untouched():
    text = "no secrets here, just what=snowflake migration"
    assert redact(text) == text


def test_request_line_strips_credentials():
    line = request_line(
        "https://api.adzuna.com/v1/api/jobs/us/search/1",
        {"app_id": _ID, "app_key": _KEY, "what": "snowflake migration"},
    )
    assert line == "/v1/api/jobs/us/search/1 what=snowflake migration"
    assert _ID not in line and _KEY not in line


def test_request_line_path_only():
    assert request_line("https://hn.algolia.com/api/v1/search_by_date") == "/api/v1/search_by_date"


def test_redacting_filter_masks_message_with_args():
    flt = RedactingFilter()
    record = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1, 'HTTP Request: GET %s "HTTP/1.1 200 OK"', (_ADZUNA,), None
    )
    assert flt.filter(record) is True
    message = record.getMessage()
    assert _KEY not in message
    assert "app_key=***" in message


def test_configure_logging_quiets_http_loggers_and_installs_filter():
    configure_logging()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    handlers = logging.getLogger().handlers
    assert any(any(isinstance(f, RedactingFilter) for f in h.filters) for h in handlers)


def test_polite_get_logs_redacted_request_line(monkeypatch, caplog):
    monkeypatch.setattr("time.sleep", lambda s=0: None)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with caplog.at_level(logging.INFO, logger="snowwatch"):
        polite_get(
            client,
            "https://api.adzuna.com/v1/api/jobs/us/search/1",
            label="jobs",
            params={"app_id": _ID, "app_key": _KEY, "what": "snowflake migration"},
        )
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert _ID not in logged
    assert _KEY not in logged
    assert "jobs: GET /v1/api/jobs/us/search/1" in logged
    assert "what=snowflake migration" in logged


def test_polite_get_error_message_redacted(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s=0: None)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500, json={})))
    with pytest.raises(CollectorError) as excinfo:
        polite_get(
            client,
            "https://api.adzuna.com/x",
            label="jobs",
            params={"app_key": _KEY, "what": "snowflake"},
        )
    assert _KEY not in str(excinfo.value)
