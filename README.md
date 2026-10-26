# contested

A CLI scanner that scores US-listed stocks on two 0–100 metrics:

- **Momentum** — accumulated directional engagement heat across sources.
- **Contested** — how evenly bulls and bears are fighting (both camps must be loud).

Calibration anchors: `l_low`/`l_high` map the low/high anchor tickers to 10 and 100.
Default `l_low=1.0`, `l_high=7.0`; refit with `contested calibrate --low MMM --high GME`.

## Setup

```bash
python -m pip install -e .
contested update-tickers     # downloads the full US ticker list to data/tickers_us.txt
```

Set credentials via environment (only what you enable):

```bash
export REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=...   # optional; falls back to public .json
export GROK_BASE_URL=https://api.x.ai GROK_API_KEY=...  # required if x_grok enabled
```

Edit `contested.toml` to enable/disable sources and set the score window.
Facebook and Instagram ship as disabled stubs (no public access path in v1).

## Usage

```bash
contested watch --once            # run one collector cycle (or: watch --every 15m)
contested scan                    # ranked list over the watchlist (default)
contested scan --market --top 20  # market-wide discovery
contested scan --json             # machine-readable
contested ticker GME              # deep dive: split, top posts per side, history
contested sources                 # per-source status
contested calibrate --low MMM --high GME   # refit anchors from real data
```

## Sources

| Source | Access | v1 |
|---|---|---|
| reddit | OAuth (optional) / public `.json` | enabled |
| x_grok | Grok `x_search` endpoint | enabled (needs `GROK_*`) |
| stocktwits | public API | enabled |
| fourchan | `a.4cdn.org` catalog (`/biz/`) | enabled |
| facebook | stub | disabled |
| instagram | stub | disabled |

Market mode scans the cheap sources market-wide, then queries X only for
watchlist ∪ top-50 tickers by cheap-source engagement (cost control).

## Manual live check

```bash
python scripts/smoke_live.py
```

## Tests

```bash
python -m pytest
```
