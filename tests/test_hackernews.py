from __future__ import annotations

from snowwatch.collectors.hackernews import HackerNewsCollector

_TERM = "snowflake costs"


def _hit(**over) -> dict:
    hit = {
        "objectID": "42",
        "title": "Snowflake costs are out of control",
        "comment_text": "<p>Our bill doubled &amp; the queries are slow.</p><p>See docs&#x2F;pricing.</p>",
        "created_at_i": 1_700_000_000,
        "author": "de_person",
        "points": 12,
        "num_comments": 3,
    }
    hit.update(over)
    return hit


def test_html_stripped_from_excerpt():
    sig = HackerNewsCollector._to_signal(_hit(), _TERM)
    assert "<p>" not in sig.text_excerpt
    assert "</p>" not in sig.text_excerpt


def test_entities_decoded():
    sig = HackerNewsCollector._to_signal(_hit(), _TERM)
    assert "&amp;" not in sig.text_excerpt
    assert "bill doubled & the queries" in sig.text_excerpt
    assert "docs/pricing" in sig.text_excerpt


def test_recurring_thread_excluded_by_title():
    hit = _hit(title="Ask HN: Who is hiring? (July 2026)")
    assert HackerNewsCollector._to_signal(hit, _TERM) is None


def test_recurring_thread_excluded_by_story_title():
    hit = _hit(title=None, story_title="Ask HN: Who wants to be hired? (July 2026)")
    assert HackerNewsCollector._to_signal(hit, _TERM) is None


def test_normal_thread_kept():
    sig = HackerNewsCollector._to_signal(_hit(), _TERM)
    assert sig is not None
    assert sig.source == "hackernews"
