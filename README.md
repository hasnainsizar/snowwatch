# snowwatch

A competitive displacement signal monitor. Snowwatch tracks public signals of
Snowflake customer pain — cost complaints, migration chatter, performance gripes,
vendor comparisons — and rolls them into a weekly digest built for sales
outreach targeting.

It runs entirely offline after collection: no LLM calls, no paid APIs, no
browser automation. Storage is a single SQLite file.

## Why displacement signals matter for GTM

The best time to reach a prospect is when they are already unhappy with what they
have. Someone publicly complaining that their Snowflake bill doubled, or posting
a "migrating off Snowflake" job req, is a warmer lead than any cold list. These
signals surface in the open — Hacker News threads, subreddit posts, job
descriptions — but they are scattered and decay fast.

Snowwatch aggregates them, scores intent, tags the type of pain, and hands sales
a ranked list with a suggested angle for each high-score account. Instead of
spraying a segment, reps work a short list of people who just told the internet
they have the exact problem you solve.

## Data sources

- **Hacker News** via the public Algolia API (`hn.algolia.com/api`). Searches
  comments and stories for the configured cost/migration terms.
- **Reddit** via the public `.json` search endpoints for r/dataengineering,
  r/snowflake, and r/databricks. Uses a real User-Agent and a courtesy delay.
  Note: Reddit blocks requests from many datacenter/cloud IPs with a 403; when
  that happens the source is logged and skipped, and the rest of the run
  continues. Run from a residential IP to collect Reddit signals.
- **Job postings** via a pluggable `JobSource`. With no credentials it uses an
  offline stub so the pipeline always runs. Set `ADZUNA_APP_ID` and
  `ADZUNA_APP_KEY` in the environment to switch to live Adzuna data
  automatically — see [Adding a job API key](#adding-a-job-api-key).

If any single source fails, snowwatch logs the error and continues with the
others.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Python 3.11+.

## Usage

```bash
snowwatch collect      # run all collectors, store new signals
snowwatch digest       # render the trailing-7-day digest (markdown + HTML)
snowwatch stats        # counts by source, category, and week
snowwatch run          # collect + digest in one shot
```

Common options:

```bash
snowwatch collect --db signals.db
snowwatch digest --days 14 --out digests
```

Digests are written to `digests/digest-YYYYMMDD.md` and `.html`.

## Sample digest

The digest opens with a source summary, then top signals ranked by score, the
same signals grouped by category, any new companies detected in the window, and
a tailored outreach angle for every signal above the high-score threshold.

```
# Snowwatch Weekly Digest
Generated 2026-07-20 18:10 UTC · trailing 7 days · 5 signals

## Top signals by score
1. [97] MIGRATION_INTENT — Senior Data Engineer — Snowflake Migration
   Company: Northwind Analytics · Source: jobs · 2026-07-18
   > We are replatforming off Snowflake to reduce compute cost...
2. [65] COST_PAIN — Analytics Engineer (Cost Optimization Snowflake)
   Company: Brightloom Inc · Source: jobs · 2026-07-15
   > Our Snowflake bill is growing fast...
```

### Screenshot

The HTML digest (`digests/digest-*.html`) is a self-contained, styled page —
open it in a browser. Score badges turn orange above the outreach threshold,
signals are carded by rank, and each outreach angle is called out in its own
block. Drop a screenshot of your first rendered digest here.

## How scoring works

Scoring is rule-based and lives in `scoring.py`; the weights and phrase lists
live in `config.py` so they are editable without touching logic. Each signal
starts at zero and accrues points:

| Contribution            | Points | Trigger                                    |
|-------------------------|--------|--------------------------------------------|
| Migration intent        | 45     | "migrating off snowflake", "replatform"... |
| Cost pain               | 30     | "snowflake bill", "too expensive"...       |
| Performance complaint   | 18     | "slow query", "warehouse is slow"...       |
| Vendor comparison       | 15     | "databricks", "vs snowflake"...            |
| General negativity      | 8      | "frustrated", "nightmare", "regret"...     |
| Company detected        | 12     | an org name extracted from the text        |
| Recency bonus           | 0–10   | full for ≤3 days old, tapering to 14 days  |
| Engagement bonus        | 0–8    | upvotes + comments on the source post      |

The buckets are additive and the total is capped at 100, so explicit migration
intent outranks cost complaints, which outrank softer negativity — matching how
a rep would prioritize the list.

**Company extraction** is a heuristic: it looks for `we at X`, `at X`, and
legal-suffix patterns (`X Inc`, `X Technologies`), then filters common
capitalized words and "Snowflake" itself via a stopword list.

**Classification** (`classifier.py`) assigns exactly one category per signal —
`MIGRATION_INTENT`, `COST_PAIN`, `PERFORMANCE_COMPLAINT`, `VENDOR_COMPARISON`,
or `OTHER` — resolved in that priority order so the strongest buy-signal wins.

**Outreach angles** are template-based, keyed off the category. Cost pain maps
to a TCO comparison, migration intent to a migration-accelerator offer, and so
on. See `OUTREACH_ANGLES` in `digest.py`.

## Adding a job API key

The default `StubJobSource` keeps the pipeline runnable with no keys. To pull
live postings from [Adzuna](https://developer.adzuna.com/) (free tier):

1. Register for an app id and key.
2. Export them before running:

   ```bash
   export ADZUNA_APP_ID=your_id
   export ADZUNA_APP_KEY=your_key
   snowwatch collect
   ```

`default_job_source()` detects the variables and switches to `AdzunaJobSource`
automatically. To add a different provider, implement the `JobSource` protocol
(`fetch(client, terms) -> list[Signal]`) in `collectors/jobs.py` and return it
from `default_job_source()`.

## Configuration

Edit `snowwatch/config.py` to change query terms, subreddits, scoring weights,
the phrase buckets, request delays, and the digest window. No other file needs
to change for tuning.

## Tests

```bash
pytest
```

Covers scoring order and bounds, company extraction, dedupe, classification, and
digest rendering against fixture data.

## Project layout

```
snowwatch/
  config.py         query terms, weights, phrase buckets
  models.py         Signal dataclass + url hashing
  collectors/       one collector per source + pluggable JobSource
  scoring.py        rule-based score + company extraction
  classifier.py     single-category tagging
  db.py             SQLite storage, dedupe, queries
  digest.py         digest assembly + outreach angles
  pipeline.py       collect -> enrich -> store orchestration
  cli.py            Typer commands
templates/          markdown + HTML digest templates
tests/              pytest suite with fixtures
```
