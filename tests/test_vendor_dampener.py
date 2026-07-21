from __future__ import annotations

from datetime import datetime, timedelta, timezone

from snowwatch import classifier, config, db, digest
from snowwatch.models import STUB_SOURCE, Signal
from snowwatch.pipeline import enrich
from snowwatch.scoring import is_staffing_company

_SKILLS_BODY = (
    "Required skills: experience with Snowflake, Databricks, Redshift, BigQuery - 5+ years. "
    "Strong Python and Spark background, hands-on with dbt."
)
_EVAL_BODY = (
    "We are evaluating Databricks as an alternative to Snowflake and running a POC to "
    "compare the two warehouses."
)


def _job(title: str, body: str, company: str | None = None, age: int = 2) -> Signal:
    return Signal(
        source="jobs",
        url=f"https://jobs.example.com/postings/{abs(hash((title, body))) % 10000}",
        title=title,
        text_excerpt=body,
        author=company or "unknown",
        posted_at=datetime.now(timezone.utc) - timedelta(days=age),
        company=company,
    )


def test_skills_list_job_classifies_other_below_floor():
    sig = _job("Senior Data Engineer", _SKILLS_BODY, company="Acme Data Inc")
    enrich([sig])
    assert sig.category == classifier.OTHER
    assert sig.score < config.DIGEST_MIN_SCORE


def test_evaluative_job_is_vendor_comparison():
    sig = _job("Data Architect", _EVAL_BODY, company="Acme Data Inc")
    enrich([sig])
    assert sig.category == classifier.VENDOR_COMPARISON


def test_migration_stub_text_still_scores_high():
    sig = Signal(
        source=STUB_SOURCE,
        url="https://jobs.example.com/postings/stub-1",
        title="Senior Data Engineer — Snowflake Migration",
        text_excerpt=(
            "We are replatforming off Snowflake to reduce compute cost. Lead the "
            "Snowflake migration to a lakehouse and own cost optimization across the pipeline."
        ),
        author="Northwind Analytics",
        posted_at=datetime.now(timezone.utc) - timedelta(days=2),
        company="Northwind Analytics",
    )
    enrich([sig])
    assert sig.category == classifier.MIGRATION_INTENT
    assert sig.score >= 90


def test_hn_comparison_comment_unaffected():
    sig = Signal(
        source="hackernews",
        url="https://news.ycombinator.com/item?id=cmp1",
        title="Warehouse bake-off",
        text_excerpt="We compared snowflake and databricks for our warehouse before deciding.",
        author="commenter",
        posted_at=datetime.now(timezone.utc),
    )
    enrich([sig])
    assert sig.category == classifier.VENDOR_COMPARISON


def test_dampener_is_jobs_specific():
    body = _SKILLS_BODY
    hn = Signal(
        source="hackernews", url="https://news.ycombinator.com/item?id=sk1",
        title="Our stack", text_excerpt=body, author="x",
        posted_at=datetime.now(timezone.utc),
    )
    job = _job("Engineer", body, company="Acme Data Inc")
    enrich([hn, job])
    assert hn.category == classifier.VENDOR_COMPARISON
    assert job.category == classifier.OTHER


def test_staffing_company_detection():
    assert is_staffing_company("Globex Technologies LLC")
    assert is_staffing_company("Bright Infotech")
    assert is_staffing_company("Cognizant")
    assert is_staffing_company("Apex Systems")
    assert not is_staffing_company("Northwind Analytics")
    assert not is_staffing_company(None)


def test_staffing_flag_set_on_signal():
    sig = _job(
        "Snowflake migration lead",
        "Lead the snowflake migration and replatform off snowflake to cut cost.",
        company="Globex Technologies LLC",
    )
    enrich([sig])
    assert sig.staffing_flag is True
    assert sig.category == classifier.MIGRATION_INTENT


def test_staffing_note_rendered(tmp_path):
    path = str(tmp_path / "t.db")
    sig = _job(
        "Snowflake migration lead",
        "Lead the snowflake migration and replatform off snowflake to reduce cost.",
        company="Globex Technologies LLC",
    )
    enrich([sig])
    with db.connect(path) as conn:
        db.insert_signals(conn, [sig])
        data = digest.build_digest_data(conn, 14)
        md = digest.render_markdown(data)
        html = digest.render_html(data)
    assert any(s.staffing_flag for s in data.top_signals)
    assert "via staffing" in md
    assert "via staffing" in html
