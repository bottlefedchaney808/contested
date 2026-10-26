# Contested Sentiment Scanner — Design

Date: 2026-10-26
Status: approved (design gate passed in session 2026-10-26)

## Purpose

A CLI tool that scores **US-listed stocks** on two 0–100 metrics:

- **Momentum** — accumulated engagement heat on a ticker across sources.
- **Contested** — how hard bulls and bears are fighting: both camps must be
  loud. One side silent → contested = 0.

Calibration anchors (user-specified): GameStop in 2021 lands ≈ 100 on both
metrics; 3M in a normal week lands ≈ 10 on momentum. Anchors are
configurable and refittable via `contested calibrate`.

## Scope (v1)

In scope:
- Sources: Reddit, X (via Grok x_search endpoint), Stocktwits, 4chan.
- Facebook, Instagram: adapters present but **disabled by default** (no public
  API for arbitrary content; behind config flag, ready for an access method
  supplied later).
- Two modes: **watchlist** (user file) and **market-wide discovery** (tickers
  surfaced by mention volume from stored events).
- On-demand `scan` + scheduled `watch` collector sharing one SQLite store.
- CLI output as ranked text list; `--json` for machine output.

Non-goals (v1):
- Trading signals, orders, alerts to external channels.
- LLM-based classification (deterministic lexicon only; LLM is a later flag).
- Sub-hour resolution, web dashboard, multi-user, backfill of historical
  archives (GME-2021 anchor is a synthetic fixture until real data accrues).

## Architecture

One Python package `contested` (Python ≥ 3.11), four layers:

```
sources/   (reddit, x_grok, stocktwits, fourchan, facebook, instagram)
  → normalizer   (tickers, dedupe, raw events → Event)
  → store        (SQLite: events, scores, source_health)
  → scorer       (sentiment, intensity, heat, momentum, contested)
  → cli          (typer: scan, watch, ticker, calibrate, sources)
```

Each layer is independently importable and testable. No web framework.
Dependencies: `typer`, `httpx`, stdlib `sqlite3`, `tomllib`/`tomli-w` for
config. No pandas, no ORM.

### Project layout

```
contested/
  pyproject.toml
  README.md
  docs/superpowers/specs/2026-10-26-contested-sentiment-scanner-design.md
  src/contested/
    __init__.py
    cli.py            # typer app, all commands
    config.py         # config load (config.toml + env), defaults
    models.py         # RawPost, Event, Score dataclasses
    normalizer.py     # ticker extraction, dedupe keying
    store.py          # SQLite access layer
    sentiment.py      # lexicon + classification
    scorer.py         # heat, momentum, contested, normalization
    calibrate.py      # anchor refit
    watch.py          # collector loop
    sources/
      __init__.py     # registry, enabled-set resolution
      base.py         # Source interface, SourceError
      reddit.py
      x_grok.py
      stocktwits.py
      fourchan.py
      facebook.py     # disabled by default
      instagram.py    # disabled by default
  tests/
    test_sentiment.py
    test_normalizer.py
    test_scorer.py
    test_store.py
    fixtures/         # recorded HTTP + synthetic score fixtures
  data/               # gitignored: watchlist, ticker list, db
```

## Components

### Source interface

```python
class Source(Protocol):
    name: str
    def fetch(self, tickers: list[str], window: TimeWindow) -> list[RawPost]: ...
```

- `RawPost(source, post_id, author, text, ts, upvotes, comments, reposts, url)`.
- Any failure raises `SourceError`; the collector catches per source.

### Adapters

| Source | Access | Notes |
|---|---|---|
| reddit | OAuth (user bot account: env `REDDIT_CLIENT_ID/SECRET`) with public `.json` fallback | Subs: wallstreetbets, stocks, investing, Options + per-ticker search |
| x_grok | Grok endpoint (`GROK_BASE_URL`, `GROK_API_KEY` env), x_search queries per `$CASHTAG` | Cost control: market mode queries X only for watchlist ∪ top-50 tickers by engagement from cheap sources |
| stocktwits | public API | stream/search per ticker |
| fourchan | public board JSON (`/biz/`) | threads + replies |
| facebook | stub, `enabled = false` default | config flag; no access path in v1 |
| instagram | stub, `enabled = false` default | config flag; no access path in v1 |

### Normalizer

- Ticker extraction: `$CASHTAG` (strong signal) or bare word-boundary match
  (length ≥ 3, case-insensitive); both validated against the loaded US ticker
  list — anything not US-listed is dropped.
- Ticker list: `data/tickers_us.txt` (downloaded once at first run; bundled
  S&P 500 fallback).
- Dedupe key: `(source, post_id)` — re-runs never double-count.

### Store (SQLite)

```sql
events(id INTEGER PK, source TEXT, post_id TEXT, author TEXT, text TEXT,
       ts TEXT, sentiment TEXT, intensity REAL, engagement REAL, url TEXT,
       created_at TEXT, UNIQUE(source, post_id))
event_tickers(event_id INTEGER, ticker TEXT, PRIMARY KEY(event_id, ticker))
scores(ticker TEXT, ts TEXT, window_hours INTEGER,
       momentum REAL, contested REAL,
       bull_heat REAL, bear_heat REAL, n_bull INTEGER, n_bear INTEGER,
       PRIMARY KEY(ticker, ts, window_hours))
source_health(source TEXT, ts TEXT, status TEXT, note TEXT)
```

Append-only events; scores are recomputable snapshots.

## Scoring

Per ticker, per window (default 7 days), with exponential recency decay,
half-life 48h: `w = exp(-ln2 · age_hours / 48)`.

1. **Sentiment** (lexicon, deterministic): bull/bear keyword sets with
   finance-specific terms (long, moon, rip, dip, accumulate, breakout, upside
   / short, SELL, top, overvalued, dump, bankruptcy, delist, bagholder, exit).
   Post is **bull**, **bear**, **neutral**, or **mixed** (both signals above
   threshold → mixed, counted in both camps at 0.6× weight).
2. **Intensity** `I ∈ [1.0, 4.0]`: base 1.0; +1.0 emphasis (caps ratio > 0.3,
   ≥2 `!`, strong modals); +1.0 conviction phrases ("all in", "I'm in",
   "bought", "sold everything", "YOLO"); +1.0 author repetition (≥3 posts,
   same stance, same window). Capped at 4.
3. **Engagement weight** `E = log10(1 + upvotes + 4·comments + 2·reposts)`.
4. **Heat** per camp: `H_c = Σ I · E · (0.6 if mixed) · w`.
5. **Momentum**: raw `R_m = H_bull + H_bear`, log-banded:
   `momentum = clamp(round(10 + 90 · (L(R_m) − L_low)/(L_high − L_low)), 0, 100)`
   where `L(x) = log10(1 + x)` and `L_low`, `L_high` are calibrated anchors
   (defaults seeded from the synthetic 3M ≈ 10 and GME-2021 ≈ 100 fixtures).
6. **Contested**: balance × heat.
   `B = 2·min(H_bull, H_bear)/(H_bull + H_bear)` (0 if either heat < floor,
   floor default 1.0 weighted unit); raw `R_c = B · R_m`; same log band.
7. **Calibration**: `contested calibrate --low TICKER --high TICKER` measures
   the two tickers' current L values and writes `L_low`/`L_high` to config.

### Cost control (market mode)

Cheap sources (Reddit, Stocktwits, 4chan) are scanned market-wide per cycle
(Reddit = poll hot subs and extract tickers from posts, not per-ticker search;
Stocktwits = global stream; 4chan = board poll); X queries are issued only
for watchlist ∪ top-50 tickers by cheap-source engagement. FB/IG never
fetched unless explicitly enabled.

## CLI

```
contested scan [--window 7d] [--top 25] [--market] [--watchlist PATH]
               [--fetch] [--source NAME ...] [--json]
contested watch [--every 15m] [--once]
contested ticker TICKER [--window 7d] [--top-posts 5] [--json]
contested calibrate --low TICKER --high TICKER
contested sources
```

- `scan` reads the store (runs collectors if `--fetch` given); default mode is
  watchlist, `--market` enables discovery.
- Output line: `#  TIKER  MOMENTUM  CONTESTED  BULL  BEAR  Δ7d`.
- `ticker` deep-dive: split, top post per side (evidence), history sparkline.
- Every scan prints source health:
  `sources: reddit✓ x_grok✓ stocktwits✓ fourchan✓ facebook– instagram–`.

## Configuration

`contested.toml` in cwd or `~/.config/contested/`:

```toml
[sources.reddit]      enabled = true
[sources.x_grok]      enabled = true
[sources.stocktwits]  enabled = true
[sources.fourchan]    enabled = true
[sources.facebook]    enabled = false
[sources.instagram]   enabled = false

[scores]
window = "7d"
half_life_hours = 48
l_low = 1.0          # L(x) of anchor-low raw momentum
l_high = 7.0         # L(x) of anchor-high raw momentum
contested_floor = 1.0

[watchlist]
path = "data/watchlist.txt"
```

Secrets via env only: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`,
`GROK_BASE_URL`, `GROK_API_KEY`.

## Error handling

- Adapters fail independently: `SourceError` → recorded in `source_health`,
  logged, other sources continue. Scan degrades to stored events.
- Transient HTTP errors: 2 retries with backoff, then source-level failure.
- Empty store → scan exits with a clear message suggesting `contested watch --once`.
- Config errors (bad path, missing creds for an enabled source) fail fast at
  startup with a named-remediation message.

## Testing

- `pytest`; no live network in CI (recorded HTTP fixtures per source).
- Scorer fixtures (the acceptance bar):
  - **gme_2021**: huge, balanced synthetic event set → momentum 100, contested 100.
  - **3m_quiet**: tiny balanced set → momentum ≈ 10, contested low.
  - **one_sided**: all-bull set → contested 0.
  - Mixed-post 0.6× double-counting; decay math (48h half-life); intensity
    caps; dedupe by (source, post_id); cashtag vs bare-mention extraction.
- Live smoke script (manual, not CI): one fetch per enabled source.

## Deferred / open

- FB/IG live ingestion — blocked on access method; adapters are stubs.
- LLM refinement for ambiguous posts (`--llm` flag).
- Reclassification pass: v1 classifies at ingest; a lexicon change only
  affects newly fetched events until a `reindex` command exists.
- Dashboard (would sit on the same package + SQLite).
- Real GME-2021 backfill (anchor is synthetic until data accrues).
