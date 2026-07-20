"""Editable configuration: query terms, source settings, and scoring weights.

Everything a non-programmer might reasonably want to tune lives here so the
pipeline logic in the other modules stays untouched.
"""

from __future__ import annotations

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
