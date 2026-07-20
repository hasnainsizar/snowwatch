"""Editable configuration: query terms, source settings, and scoring weights.

Everything a non-programmer might reasonably want to tune lives here so the
pipeline logic in the other modules stays untouched.
"""

from __future__ import annotations

import os

# --- Credentials (read from environment, never hard-coded) -----------------
# Reddit script-app credentials enable the authenticated API; absent, the
# collector falls back to the public JSON endpoints. Adzuna keys switch the job
# collector from the offline stub to live postings.
REDDIT_CLIENT_ID: str | None = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET: str | None = os.environ.get("REDDIT_CLIENT_SECRET")
ADZUNA_APP_ID: str | None = os.environ.get("ADZUNA_APP_ID")
ADZUNA_APP_KEY: str | None = os.environ.get("ADZUNA_APP_KEY")

# Terms fed to every text-search collector. Keep them lowercase; matching is
# case-insensitive.
QUERY_TERMS: list[str] = [
    "snowflake costs",
    "snowflake bill",
    "snowflake pricing",
    "migrating off snowflake",
    "leaving snowflake",
    "snowflake too expensive",
    "snowflake credits",
]

# Terms used specifically for job-posting collectors.
JOB_QUERY_TERMS: list[str] = [
    "snowflake migration",
    "replatform snowflake",
    "cost optimization snowflake",
]

# Subreddits searched via the public JSON endpoints.
SUBREDDITS: list[str] = ["dataengineering", "snowflake", "databricks"]

# Sent on every outbound request. Reddit blocks generic/empty agents.
USER_AGENT: str = "snowwatch/0.1 (competitive signal monitor; contact ops@example.com)"

# Seconds to sleep between successive HTTP calls to the same host.
REQUEST_DELAY_SECONDS: float = 1.5

# Per-request network timeout.
REQUEST_TIMEOUT_SECONDS: float = 20.0

# Trailing window used by the digest and stats commands.
DIGEST_WINDOW_DAYS: int = 7

# Default SQLite location relative to the current working directory.
DEFAULT_DB_PATH: str = "snowwatch.db"


# --- Scoring weights -------------------------------------------------------
# Signal intent is weighted so explicit migration intent outranks cost
# complaints, which outrank general negativity. Values are additive points
# capped at 100 downstream.

WEIGHTS: dict[str, int] = {
    "migration_intent": 45,
    "cost_pain": 30,
    "performance_complaint": 18,
    "vendor_comparison": 15,
    "general_negativity": 8,
    "company_detected": 12,
    "recency_bonus": 10,
    "engagement_bonus": 8,
    # Subtracted when a signal is inbound (moving TO Snowflake) so it sinks
    # below genuine displacement signals.
    "migration_inbound_penalty": 30,
}

# Phrase buckets that drive both scoring and classification. Ordered loosely by
# strength within each bucket. Lowercase, substring-matched.
SIGNAL_PHRASES: dict[str, list[str]] = {
    "migration_intent": [
        "migrating off snowflake",
        "migrate off snowflake",
        "moving off snowflake",
        "moving away from snowflake",
        "leaving snowflake",
        "replatform",
        "replatforming",
        "ripping out snowflake",
        "switching from snowflake",
        "replacing snowflake",
        "snowflake migration",
    ],
    "cost_pain": [
        "snowflake costs",
        "snowflake cost",
        "snowflake bill",
        "snowflake pricing",
        "too expensive",
        "cost optimization",
        "cost explosion",
        "credits are burning",
        "burning credits",
        "runaway cost",
        "compute cost",
        "sticker shock",
    ],
    "performance_complaint": [
        "slow query",
        "slow queries",
        "query performance",
        "warehouse is slow",
        "timeout",
        "spilling to disk",
        "concurrency issues",
    ],
    "vendor_comparison": [
        "databricks",
        "bigquery",
        "redshift",
        "clickhouse",
        "duckdb",
        "vs snowflake",
        "snowflake vs",
        "compared to snowflake",
    ],
    "general_negativity": [
        "frustrated",
        "nightmare",
        "hate",
        "fed up",
        "disappointed",
        "regret",
        "painful",
    ],
}

# Inbound migration phrases: people moving TO Snowflake. These are the opposite
# of displacement intent and must not score as such. Lowercase, substring match.
MIGRATION_INBOUND_PHRASES: list[str] = [
    "migrating to snowflake",
    "migrate to snowflake",
    "migration to snowflake",
    "moving to snowflake",
    "move to snowflake",
    "moving onto snowflake",
    "switching to snowflake",
    "switched to snowflake",
    "adopting snowflake",
    "onboarding to snowflake",
    "standardizing on snowflake",
    "consolidating on snowflake",
]

# Positive-context phrases that dampen cost/performance/negativity buckets: a
# satisfied mention should not register as pain. Lowercase, substring match.
POSITIVE_CONTEXT_PHRASES: list[str] = [
    "snowflake is great",
    "snowflake is awesome",
    "snowflake is fantastic",
    "love snowflake",
    "happy with snowflake",
    "pricing is fair",
    "worth the cost",
    "worth every",
    "great value",
    "no complaints",
    "works great",
    "recommend snowflake",
]

# Technology, vendor, and cloud terms that are frequently capitalized in this
# domain but are never a prospect company name. Matched case-insensitively.
COMPANY_DENYLIST: frozenset[str] = frozenset(
    {
        "Snowflake",
        "Databricks",
        "Redshift",
        "BigQuery",
        "ClickHouse",
        "DuckDB",
        "Postgres",
        "PostgreSQL",
        "MySQL",
        "Oracle",
        "Teradata",
        "Spark",
        "Kafka",
        "Airflow",
        "Hadoop",
        "Presto",
        "Trino",
        "Iceberg",
        "Fivetran",
        "Airbyte",
        "Looker",
        "Tableau",
        "AWS",
        "GCP",
        "Azure",
        "S3",
        "EC2",
        "EMR",
        "Athena",
        "Glue",
        "Lambda",
        "SQL",
        "NoSQL",
        "ETL",
        "ELT",
        "DBT",
        "API",
        "CSV",
        "JSON",
        "CTO",
        "CEO",
        "CFO",
        "VP",
        "OK",
        "PR",
        "AI",
        "ML",
        "LLM",
        "GPU",
        "CPU",
        "Python",
        "Java",
        "Scala",
        "Rust",
    }
)

# Common English capitalized tokens the company heuristic should never treat as
# an organization name.
COMPANY_STOPWORDS: frozenset[str] = frozenset(
    {
        "Snowflake",
        "The",
        "This",
        "That",
        "We",
        "Our",
        "My",
        "I",
        "A",
        "An",
        "It",
        "They",
        "You",
        "SQL",
        "ETL",
        "Data",
        "Cloud",
        "AWS",
        "GCP",
        "Azure",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    }
)
