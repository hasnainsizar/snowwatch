"""Logging setup and credential redaction for anything that reaches the logs."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from . import config

# Loggers that emit full request URLs (including query strings) at INFO. Quieted
# so credentials never reach the console; snowwatch logs its own request lines.
_HTTP_LOGGERS = ("httpx", "httpcore", "httpcore.http11", "httpcore.connection")


def _build_pattern() -> re.Pattern[str]:
    # Longest names first so "app_key" wins over "key" at the same position.
    names = sorted(config.REDACT_QUERY_PARAMS, key=len, reverse=True)
    alt = "|".join(re.escape(n) for n in names)
    return re.compile(rf"(?i)(?<![\w-])({alt})=([^&\s\"'#]+)")


_PATTERN = _build_pattern()


def redact(text: str) -> str:
    """Mask the values of sensitive query params anywhere in a string."""
    return _PATTERN.sub(lambda m: f"{m.group(1)}=***", text)


def request_line(url: str, params: dict | None = None) -> str:
    """Path plus non-sensitive query params, for a one-line request log."""
    path = urlsplit(url).path or url
    if not params:
        return path
    shown = [f"{k}={v}" for k, v in params.items() if k.lower() not in config.REDACT_QUERY_PARAMS]
    return f"{path} " + " ".join(shown) if shown else path


class RedactingFilter(logging.Filter):
    """Rewrites each record's rendered message with secrets masked."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging over formatting
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging, quiet HTTP client loggers, and install redaction."""
    logging.basicConfig(level=level, format="%(levelname)s %(message)s")
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())
    for name in _HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
