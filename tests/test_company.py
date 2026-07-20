from __future__ import annotations

from datetime import datetime, timezone

import pytest

from snowwatch.models import Signal
from snowwatch.scoring import extract_company, normalize_company, score_signal


@pytest.mark.parametrize(
    "text",
    [
        "We migrated from AWS to GCP using Spark and Kafka",
        "Comparing Snowflake and Databricks on Redshift workloads",
        "The ETL runs on Airflow with DBT and Postgres",
    ],
)
def test_denylisted_tech_rejected(text):
    assert extract_company(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "We run PySpark jobs on the cluster",
        "Migrated the tables to Delta Lake last quarter",
        "Governance is handled by Unity Catalog now",
        "We track experiments with MLflow and deploy on Kubernetes",
        "Infra is all Terraform, models served on Bedrock",
    ],
)
def test_new_denylist_terms_rejected(text):
    assert extract_company(text) is None


def test_author_field_not_used_for_company():
    sig = Signal(
        source="hackernews",
        url="https://news.ycombinator.com/item?id=au1",
        title="Our snowflake bill is too expensive",
        text_excerpt="the warehouse credits keep climbing with no company named here",
        author="Bigcorp Industries",
        posted_at=datetime.now(timezone.utc),
    )
    score_signal(sig)
    assert sig.company is None


def test_context_pattern_extracts_company():
    assert extract_company("We at Northwind Analytics are leaving") == "Northwind Analytics"


def test_team_pattern_extracts_company():
    assert extract_company("Brightloom's data team is fed up") == "Brightloom"


def test_bare_capitalization_needs_repetition():
    once = extract_company("The startup Vertexeon does data work")
    twice = extract_company("Vertexeon grew fast. People say Vertexeon migrated off snowflake.")
    assert once is None
    assert twice == "Vertexeon"


def test_stopword_head_rejected():
    assert extract_company("We at Snowflake are fine") is None


def test_common_capitalized_words_rejected():
    assert extract_company("Is this slow? Is it the warehouse? Is it cost?") is None
    assert extract_company("In one case, In another case, In prod it broke") is None


def test_allcaps_keywords_rejected_in_bare_tier():
    assert extract_company("SELECT AS AND CASE WHEN; SELECT AS AND CASE WHEN") is None
    assert extract_company("The BLOB column had a BLOB and another BLOB value") is None


def test_context_still_accepts_acronym_company():
    assert extract_company("We at IBM ran the numbers. We at IBM again.") == "IBM"


def test_normalize_strips_suffix():
    assert normalize_company("Brightloom Inc") == "Brightloom"
    assert normalize_company("Northwind, LLC") == "Northwind"


def test_normalize_collapses_whitespace():
    assert normalize_company("  Acme   Data  Co ") == "Acme Data"


def test_normalize_preserves_multiword_name():
    assert normalize_company("Northwind Analytics") == "Northwind Analytics"
