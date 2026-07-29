# snowwatch

A competitive displacement signal monitor. Snowwatch tracks public signals of
Snowflake customer pain — cost complaints, migration chatter, performance gripes,
vendor comparisons — and rolls them into a periodic digest built for sales
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

Three live sources run by default, none requiring authentication:

- **Hacker News** via the public Algolia API (`hn.algolia.com/api`). Searches
  comments and stories for the configured cost/migration terms.
- **Stack Exchange** via the public API 2.3 (`api.stackexchange.com`), across
  Stack Overflow and dba.stackexchange. Uses `/search/advanced` with term-style
  queries and pulls question bodies (HTML stripped) so the scorer has real text.
  Honors the API's mandatory `backoff` field and stops early if `quota_remaining`
  runs low. An optional `STACKEXCHANGE_KEY` raises the quota but is not required.
- **Job postings** via a pluggable `JobSource`. With no credentials it uses an
  offline stub so the pipeline always runs. Set `ADZUNA_APP_ID` and
  `ADZUNA_APP_KEY` in the environment to switch to live Adzuna data
  automatically — see [Adding a job API key](#adding-a-job-api-key).

If any single source fails, snowwatch logs the error and continues with the
others.

### Reddit collector (built, gated)

The Reddit collector is fully implemented — official OAuth (client-credentials
flow), token caching until expiry, and rate-limit backoff — but it is disabled by
default. Reddit's Data API now requires prior approval under their Responsible
Builder Policy, so shipping it on by default would send unauthorized traffic.
Enabling it takes approved `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` credentials
plus the `SNOWWATCH_ENABLE_REDDIT=1` flag (or adding `reddit` to
`ENABLED_COLLECTORS` in `config.py`). While disabled, `collect` logs a single
`reddit: disabled` line and makes no network calls. Existing Reddit signals
already in the database remain valid history.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Python 3.11+.

All three default sources run with no credentials. The variables below are
optional. Copy `.env.example` to `.env`, fill in what you have, and export it
before running (`set -a; source .env; set +a`).

| Variable                  | Effect                                        |
|---------------------------|-----------------------------------------------|
| `STACKEXCHANGE_KEY`       | Raises the Stack Exchange request quota        |
| `ADZUNA_APP_ID` / `_KEY`  | Live Adzuna job postings instead of the stub   |
| `SNOWWATCH_ENABLE_REDDIT` | Set to `1` to enable the gated Reddit collector |
| `REDDIT_CLIENT_ID` / `_SECRET` | Reddit OAuth creds; only used when enabled |

## Usage

```bash
snowwatch collect      # run all collectors, store new signals
snowwatch digest       # render the trailing 14-day digest (markdown + HTML)
snowwatch stats        # counts by source, category, and week
snowwatch run          # collect + digest in one shot
snowwatch seed-stubs   # store the offline demonstration signals (safe to re-run)
snowwatch rescore      # re-apply current scoring rules to stored signals
```

`seed-stubs` exists because the jobs collector only emits stub postings when
Adzuna credentials are absent: once live keys are configured, a database can
hold no stub rows at all. Seeding stores the two demonstration signals directly,
dated inside the current window, so `digest --include-stubs` has something to
show. It dedupes on re-run.

`rescore` matters because score and category are written at collection time and
read back verbatim by the digest: after you tune `config.py`, past signals keep
their old numbers until you run it.

The digest window defaults to 14 days and is fully configurable with `--days`;
the trend line compares this period against the prior period of equal length.

Common options:

```bash
snowwatch collect --db signals.db
snowwatch digest --days 30 --out digests
```

Digests are written to `digests/digest-YYYYMMDD.md` and `.html`. A
`--include-stubs` render adds a `-stubs` suffix
(`digests/digest-YYYYMMDD-stubs.md`) so the two renders of the same day never
overwrite each other.

## Sample digest

The digest opens with a source summary and a period-over-period trend line, then
top signals ranked by score (displacement categories only), the same signals
grouped by category, new companies detected in the window, and a tailored
outreach angle for every high-score displacement signal.

![Sample snowwatch HTML digest](docs/digest-sample.png)

*The HTML digest is a self-contained styled page; score badges turn orange above
the outreach threshold. Generate one with `snowwatch digest` and drop a
screenshot at `docs/digest-sample.png`.*

```
# Snowwatch Digest — trailing 14 days
Generated 2026-07-20 18:10 UTC · trailing 14 days · 9 signals
Trend: 9 this period vs 6 prior (+3)

## Top signals by score
1. [97] MIGRATION_INTENT — Senior Data Engineer — Snowflake Migration
   Company: Northwind Analytics · Source: jobs · 2026-07-18
   > We are replatforming off Snowflake to reduce compute cost...
2. [65] COST_PAIN — Analytics Engineer (Cost Optimization Snowflake)
   Company: Brightloom Inc · Source: jobs · 2026-07-15
   > Our Snowflake bill is growing fast...
```

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

**Direction and sentiment guards.** Before points are awarded, `analyze()`
checks direction and tone. Inbound phrases ("migrating to snowflake", "switched
to snowflake") without an explicit outbound phrase drop the migration bucket and
apply a penalty, so people *adopting* Snowflake do not read as displacement.
Positive-context phrases ("snowflake is great", "pricing is fair") suppress the
cost, performance, and negativity buckets so satisfied mentions do not score as
pain. A topic guard also clears all buckets when a signal carries no
displacement phrase and none of the data-warehouse vocabulary in
`DATA_CONTEXT_TERMS`, so snow/weather or CDP "snowflake" false matches score to
OTHER. All lists live in `config.py`.

**Company extraction** uses confidence tiers. Tier one is explicit context —
`we at X`, `X's data team`, `at X`, or a legal suffix (`X Inc`) — and counts on
a single match. Tier two is bare capitalization, which must recur (2+ times) in
the same signal before it is trusted. A denylist of tech/vendor terms (AWS, DBT,
Databricks, Snowflake itself, ...) and common capitalized words is rejected at
every tier. Display names are preserved; `normalize_company` strips suffixes and
whitespace only for dedupe.

**Classification** (`classifier.py`) assigns exactly one category per signal —
`MIGRATION_INTENT`, `COST_PAIN`, `PERFORMANCE_COMPLAINT`, `VENDOR_COMPARISON`,
`MIGRATION_INBOUND`, or `OTHER` — resolved in priority order so the strongest
buy-signal wins. `MIGRATION_INBOUND` stays visible in `stats` but is excluded
from the digest's top signals and outreach.

**Outreach angles** are template-based, keyed off the category. Cost pain maps
to a TCO comparison, migration intent to a migration-accelerator offer, and so
on. See `OUTREACH_ANGLES` in `digest.py`.

## Known limitations and scoring notes

**Rule-based tradeoffs.** Scoring is deterministic phrase matching, not
comprehension. It is fully offline, fast, and auditable, and it never
hallucinates — but it misses paraphrases the phrase lists do not cover and can
over-credit a signal that stacks keywords without real intent. Tune the lists
and weights in `config.py` as your corpus teaches you what fires.

**Direction detection.** Inbound versus outbound migration is decided by
directional phrases and patterns, with outbound winning ties. Alongside the
plain "moving to/off snowflake" forms, `MIGRATION_INBOUND_PATTERNS` catches
gapped constructions such as "transitioning our data platform from Microsoft
SQL Server to Snowflake", where a source system sits between the verb and the
destination. Phrases that name a migration without a direction ("snowflake
migration", "replatform") are listed in `AMBIGUOUS_MIGRATION_PHRASES`: on their
own they still read as outbound intent, biasing toward surfacing rather than
hiding a possible signal, but they no longer outrank an inbound construction
found in the same text. Rephrasings outside both lists are still missed.

**Dedupe identity.** Signals are keyed on `urls.canonical_url`, not the raw
link, because collectors hand back per-request tracking noise: Adzuna rebuilds
its landing URLs with a fresh `se` token on every search, so one ad would
otherwise store as a new signal per collection run. Adzuna links collapse to
their stable ad id (`adzuna:5787001382`), covering both the `/land/ad/{id}` and
`/details/{id}` shapes; other sources keep the params that identify a post (the
Hacker News `item?id=`) and lose tracking params, fragments, `www.`, and case.
Databases written before canonicalization are migrated once on open: keys are
recomputed, duplicate rows merge into the earliest-posted one with the union of
their matched terms, and the count is logged.

Stub postings get their own `stub:<path>` namespace. Because the stub and
Adzuna namespaces are disjoint from each other and from ordinary URL keys, a
demonstration signal can never share a dedupe key with a live posting and be
merged into one, and `_migrate` reasserts the `jobs-stub` source tag on every
stub row it sees.

**Company confidence.** Extraction is heuristic. Explicit context is reliable;
bare capitalization requires repetition and still yields the occasional false
name or misses a lowercase-styled brand. Treat the company field as a lead, not
ground truth, and expect the denylist to need occasional additions.

**Stack Exchange volume.** Stack Exchange yields low volume for Snowflake-pain
terms (single-digit signals per month); the collector uses a broad `snowflake`
term plus downstream scoring, rather than narrow phrases, so nothing recent is
missed, with an off-topic guard that routes snow/weather and CDP false matches
to OTHER.

**Reddit gating.** The Reddit collector is OAuth-only and off by default because
the Data API requires prior approval. Enabled with approved credentials it is
stable and rate-limit aware; enabled without credentials it errors cleanly and is
logged and skipped. See [Reddit setup](#reddit-setup).

## Reddit setup

Reddit is disabled by default. To enable it you need approved Data API access
plus the env flag:

1. Get your app approved and create an app of type **script** at
   <https://www.reddit.com/prefs/apps> (redirect URI `http://localhost`).
2. Copy the client id (under the app name) and the secret.
3. Export the credentials and the enable flag before running:

   ```bash
   export SNOWWATCH_ENABLE_REDDIT=1
   export REDDIT_CLIENT_ID=your_id
   export REDDIT_CLIENT_SECRET=your_secret
   snowwatch collect
   ```

Enabled, the collector logs `reddit: using authenticated OAuth API`. Left
disabled, `collect` logs a single `reddit: disabled (requires approved Reddit
Data API access)` line and makes no Reddit network calls. Enabling it without
credentials raises a clear error that is logged and skipped.

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

Edit `snowwatch/config.py` to change per-source query terms, scoring weights, the
phrase buckets, request delays, the digest window, and which collectors run.
`ENABLED_COLLECTORS` lists the active sources; `reddit_enabled()` gates the Reddit
collector behind that list or the `SNOWWATCH_ENABLE_REDDIT` flag. No other file
needs to change for tuning.

## Tests

```bash
pytest
```

Covers scoring order and bounds, company extraction, dedupe, classification,
collector normalization (Stack Exchange and Reddit against fixture responses),
the Reddit gating logic, and digest rendering.

## Project layout

```
snowwatch/
  config.py         per-source query terms, weights, phrase buckets, enabled set
  models.py         Signal dataclass + url hashing
  urls.py           canonical URL form behind the dedupe key
  collectors/       hackernews, stackexchange, jobs, reddit (gated) + registry
  scoring.py        rule-based score + company extraction
  classifier.py     single-category tagging
  db.py             SQLite storage, dedupe, queries
  digest.py         digest assembly + outreach angles
  pipeline.py       collect -> enrich -> store, and rescore of stored rows
  cli.py            Typer commands
templates/          markdown + HTML digest templates
tests/              pytest suite with fixtures
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the data-flow diagram and a guide to
adding a new collector.
