from __future__ import annotations

from snowwatch import db, digest
from snowwatch.pipeline import enrich


def _seed(path, signals):
    enrich(signals)
    with db.connect(path) as conn:
        db.insert_signals(conn, signals)


def test_markdown_renders(tmp_path, migration_signal, cost_signal):
    path = str(tmp_path / "t.db")
    _seed(path, [migration_signal, cost_signal])
    with db.connect(path) as conn:
        data = digest.build_digest_data(conn, 7)
        md = digest.render_markdown(data)
    assert "Snowwatch Weekly Digest" in md
    assert "migrating off Snowflake" in md
    assert "MIGRATION_INTENT" in md


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


def test_write_digest_creates_files(tmp_path, cost_signal):
    path = str(tmp_path / "t.db")
    _seed(path, [cost_signal])
    with db.connect(path) as conn:
        md_path, html_path = digest.write_digest(conn, 7, str(tmp_path / "out"))
    assert md_path.exists()
    assert html_path.exists()
    assert html_path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
