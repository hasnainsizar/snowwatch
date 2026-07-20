from __future__ import annotations

from datetime import datetime, timedelta, timezone

from snowwatch import classifier, config, db, digest
from snowwatch.models import Signal
from snowwatch.pipeline import enrich


def _seed(path, signals):
    enrich(signals)
    with db.connect(path) as conn:
        db.insert_signals(conn, signals)


def _scored(url: str, score: int, category: str) -> Signal:
    return Signal(
        source="hackernews",
        url=url,
        title="snowflake signal",
        text_excerpt="warehouse cost",
        author="a",
        posted_at=datetime.now(timezone.utc),
        score=score,
        category=category,
    )


def _seed_raw(path, signals):
    with db.connect(path) as conn:
        db.insert_signals(conn, signals)


def _inbound_signal() -> Signal:
    return Signal(
        source="reddit",
        url="https://www.reddit.com/r/dataengineering/comments/in/",
        title="We are migrating to Snowflake from Redshift",
        text_excerpt="Moving to snowflake next month, excited about it.",
        author="newbie",
        posted_at=datetime.now(timezone.utc),
    )


def test_top_signals_exclude_inbound_and_other(tmp_path, migration_signal):
    path = str(tmp_path / "t.db")
    inbound = _inbound_signal()
    _seed(path, [migration_signal, inbound])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 7)
    categories = {s.category for s in data.top_signals}
    assert classifier.MIGRATION_INBOUND not in categories
    assert classifier.OTHER not in categories
    assert classifier.MIGRATION_INTENT in categories


def test_inbound_still_visible_in_category_breakdown(tmp_path, monkeypatch, migration_signal):
    monkeypatch.setattr(config, "DIGEST_MIN_SCORE", 0)
    path = str(tmp_path / "t.db")
    _seed(path, [migration_signal, _inbound_signal()])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 7)
    assert classifier.MIGRATION_INBOUND in data.by_category


def test_trend_label_renders(tmp_path, cost_signal):
    path = str(tmp_path / "t.db")
    _seed(path, [cost_signal])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 7)
        md = digest.render_markdown(data)
    assert "Trend:" in md
    assert data.trend_label in md


def test_markdown_renders(tmp_path, migration_signal, cost_signal):
    path = str(tmp_path / "t.db")
    _seed(path, [migration_signal, cost_signal])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 7)
        md = digest.render_markdown(data)
    assert "Snowwatch Digest" in md
    assert "migrating off Snowflake" in md
    assert "MIGRATION_INTENT" in md


def test_default_window_is_14():
    assert config.DIGEST_WINDOW_DAYS == 14


def test_template_wording_driven_by_days(tmp_path, cost_signal):
    path = str(tmp_path / "t.db")
    _seed(path, [cost_signal])
    with db.connect(path) as conn:
        md14 = digest.render_markdown(digest.build_digest_data(conn, 14))
        md30 = digest.render_markdown(digest.build_digest_data(conn, 30))
    assert "trailing 14 days" in md14
    assert "trailing 30 days" in md30
    assert "Weekly" not in md14
    assert "this week" not in md14


def test_trend_compares_equal_prior_period(tmp_path):
    path = str(tmp_path / "t.db")
    now = datetime.now(timezone.utc)
    current = Signal(
        source="hackernews", url="https://news.ycombinator.com/item?id=1",
        title="snowflake bill too expensive", text_excerpt="our snowflake bill is too expensive",
        author="a", posted_at=now - timedelta(days=1),
    )
    prior = Signal(
        source="hackernews", url="https://news.ycombinator.com/item?id=2",
        title="snowflake pricing shock", text_excerpt="snowflake pricing is too expensive",
        author="b", posted_at=now - timedelta(days=12),
    )
    older = Signal(
        source="hackernews", url="https://news.ycombinator.com/item?id=3",
        title="snowflake cost", text_excerpt="snowflake bill too expensive",
        author="c", posted_at=now - timedelta(days=30),
    )
    _seed(path, [current, prior, older])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 10)
    assert data.total_signals == 1
    assert data.prior_signals == 1
    assert data.trend_delta == 0


def test_html_renders_and_escapes(tmp_path, migration_signal):
    path = str(tmp_path / "t.db")
    _seed(path, [migration_signal])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 7)
        html = digest.render_html(data)
    assert "<!DOCTYPE html>" in html
    assert "Suggested outreach angles" in html


def test_outreach_angle_keyed_by_category(tmp_path, migration_signal):
    path = str(tmp_path / "t.db")
    _seed(path, [migration_signal])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 7)
    assert data.outreach, "high-score migration signal should produce an angle"
    _, angle = data.outreach[0]
    assert "migration accelerator" in angle


def test_new_companies_detected(tmp_path, migration_signal):
    path = str(tmp_path / "t.db")
    _seed(path, [migration_signal])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 7)
    assert "Northwind Analytics" in data.new_companies


def test_low_score_suppressed_from_categories(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_raw(path, [_scored("u1", 40, classifier.COST_PAIN), _scored("u2", 5, classifier.OTHER)])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 14)
    assert classifier.COST_PAIN in data.by_category
    assert classifier.OTHER not in data.by_category
    assert data.suppressed_low_score == 1


def test_min_score_configurable(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DIGEST_MIN_SCORE", 0)
    path = str(tmp_path / "t.db")
    _seed_raw(path, [_scored("u1", 40, classifier.COST_PAIN), _scored("u2", 5, classifier.OTHER)])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 14)
    assert classifier.OTHER in data.by_category
    assert data.suppressed_low_score == 0


def test_low_score_still_visible_in_stats(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_raw(path, [_scored("u1", 40, classifier.COST_PAIN), _scored("u2", 5, classifier.OTHER)])
    with db.connect(path) as conn:
        assert db.total_count(conn) == 2
        assert len(db.signals_since(conn, 14)) == 2


def test_suppressed_footer_rendered(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_raw(
        path,
        [
            _scored("u1", 40, classifier.COST_PAIN),
            _scored("u2", 5, classifier.OTHER),
            _scored("u3", 2, classifier.OTHER),
        ],
    )
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 14)
        md = digest.render_markdown(data)
        html = digest.render_html(data)
    assert data.suppressed_low_score == 2
    assert "2 low-score signals suppressed — see stats." in md
    assert "2 low-score signals suppressed" in html


def test_no_footer_when_none_suppressed(tmp_path):
    path = str(tmp_path / "t.db")
    _seed_raw(path, [_scored("u1", 40, classifier.COST_PAIN)])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 14)
        md = digest.render_markdown(data)
    assert data.suppressed_low_score == 0
    assert "suppressed" not in md


def test_write_digest_creates_files(tmp_path, cost_signal):
    path = str(tmp_path / "t.db")
    _seed(path, [cost_signal])
    with db.connect(path) as conn:
        md_path, html_path = digest.write_digest(conn, 7, str(tmp_path / "out"))
    assert md_path.exists()
    assert html_path.exists()
    assert html_path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
