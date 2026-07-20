# Architecture

Snowwatch is a linear pipeline over a single SQLite store. Collectors normalize
external sources into `Signal` records; enrichment scores and classifies them;
the digest reads back the trailing window and renders it.

## Data flow

```
                 +-------------------------------------------+
                 |                collectors/                |
                 |  hackernews   reddit(oauth|public)  jobs  |
                 +---------------------+---------------------+
                                       | list[Signal]
                                       v
                          +------------------------+
                          |   pipeline.enrich()    |
                          |  scoring + classifier  |
                          +-----------+------------+
                                      | scored, categorized signals
                                      v
                          +------------------------+
                          |   db (SQLite)          |
                          |  dedupe by url_hash    |
                          +-----------+------------+
                                      | signals_since(window)
                                      v
                          +------------------------+
                          |   digest.py            |
                          |  markdown + HTML       |
                          +------------------------+
```

Each stage is pure and independently testable:

- `scoring.analyze()` resolves direction (inbound vs outbound migration) and
  sentiment, then returns the effective phrase buckets. Both `score_signal` and
  `classifier.classify` consume it, so a signal cannot score as displacement
  pain while being classified as inbound.
- `db` enforces dedupe at the schema level (`UNIQUE url_hash`, `INSERT OR
  IGNORE`), so re-running `collect` is idempotent.
- `digest.build_digest_data` is the only place that decides what a digest shows;
  templates are dumb.

## Adding a new collector

1. Create `snowwatch/collectors/<source>.py` with a class exposing
   `name: str` and `collect(self, client: httpx.Client) -> list[Signal]`.
   Return normalized `Signal` records; set `matched_terms` to the query term
   that surfaced each hit. Use `base.polite_get` for the courtesy delay and
   unified error handling.
2. Raise `CollectorError` on failure. `pipeline.collect_all` logs it and
   continues with the other sources, so one bad source never aborts a run.
3. Register the class in `ALL_COLLECTORS` in `snowwatch/collectors/__init__.py`.
4. Put any query terms, endpoints, or credentials in `config.py` rather than the
   collector body.

Scoring, classification, storage, and the digest pick up the new source with no
further changes.
