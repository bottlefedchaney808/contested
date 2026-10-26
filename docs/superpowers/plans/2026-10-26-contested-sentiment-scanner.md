# Contested Sentiment Scanner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `contested`, a Python CLI that scores US-listed stocks on two 0–100 metrics — **Momentum** (accumulated directional engagement heat) and **Contested** (how evenly bulls and bears are fighting) — from Reddit, X (via a Grok endpoint), Stocktwits, and 4chan, with Facebook/Instagram as disabled stubs, persisting events in SQLite.

**Architecture:** One Python package, four layers: `sources/` (per-platform fetchers behind a common protocol) → `normalizer` (ticker extraction + dedupe → `Event`) → `store` (SQLite) → `scorer` (sentiment heat → momentum/contested), surfaced by a `typer` CLI with an on-demand `scan` and a scheduled `watch` collector.

**Tech Stack:** Python ≥ 3.11 (dev machine has 3.15), `typer`, `httpx`, stdlib `sqlite3` + `tomllib`, `tomli-w`; `pytest` for tests. No ORM, no pandas, no web framework.

**Spec:** `docs/superpowers/specs/2026-10-26-contested-sentiment-scanner-design.md`

## Global Constraints

- Python ≥ 3.11. On the dev machine the interpreter is `python` (3.15.0); run everything with `python` and `python -m pytest`.
- Runtime dependencies are exactly `typer`, `httpx`, `tomli-w` (plus stdlib). Do not add other runtime deps. `pytest` is dev-only.
- All tickers must be US-listed per the loaded ticker list; anything else is dropped.
- Scoring math is fixed (verbatim from spec §Scoring):
  - `engagement_weight = log10(1 + upvotes + 4·comments + 2·reposts)`
  - `decay_weight = exp(-ln2 · age_hours / half_life_hours)`, default half-life 48h
  - mixed posts count in both camps at `0.6×` weight
  - `momentum = clamp(round(10 + 90·(L(R_m) − l_low)/(l_high − l_low)), 0, 100)` where `L(x)=log10(1+x)`, `R_m = bull_heat + bear_heat`
  - `B = 2·min(bull,bear)/(bull+bear)` (0 if either heat < `contested_floor`); `R_c = B·R_m`; `contested = band(R_c)` with the same band
  - intensity `I ∈ [1,4]`: base 1 + emphasis + conviction + author-repetition (≥3 same-stance posts in window), capped at 4
- No network in tests: sources are tested with `httpx.MockTransport`; the collector is tested with in-process fake sources.
- Commit after every task. Conventional-commit style (`feat:`, `test:`, `chore:`).
- Repo-local git identity is set in Task 1; later tasks commit without extra flags.
- The package is installed editable (`python -m pip install -e .`) in Task 1 so `from contested import ...` and the `contested` console entry work in later tasks and tests.

## File Structure

```
contested/
  pyproject.toml                 # packaging, deps, console script
  README.md                      # usage, config, anchors
  .gitignore                     # data/, __pycache__, .venv, *.egg-info
  contested.toml                 # example/default config (checked in)
  src/contested/
    __init__.py                  # __version__
    __main__.py                  # python -m contested
    models.py                    # RawPost, Event, Score, TimeWindow, utcnow
    config.py                    # Config, ConfigError, parse_window, load_config, load_watchlist, resolve_config_path
    sentiment.py                 # lexicon + classify + text_intensity
    scorer.py                    # engagement/decay/band/score_ticker/score_all
    store.py                     # SQLite Store
    normalizer.py                # extract_tickers + normalize_posts
    tickerlist.py                # load_ticker_set + download_ticker_list
    calibrate.py                 # calibrate() anchor refit
    watch.py                     # run_cycle collector
    cli.py                       # typer app: scan/watch/ticker/calibrate/sources/update-tickers
    sources/
      __init__.py                # build_sources registry
      base.py                    # SourceError, Source protocol, http_get_json
      reddit.py
      stocktwits.py
      fourchan.py
      x_grok.py
      facebook.py                # stub
      instagram.py               # stub
  tests/
    conftest.py                  # shared fixtures (fake source, seeded store)
    test_config.py
    test_sentiment.py
    test_scorer.py
    test_store.py
    test_normalizer.py
    test_tickerlist.py
    test_sources_base.py
    test_sources_reddit.py
    test_sources_stocktwits.py
    test_sources_fourchan.py
    test_sources_x_grok.py
    test_sources_stubs.py
    test_sources_registry.py
    test_watch.py
    test_calibrate.py
    test_cli.py
    fixtures/
      tickers.txt
  data/                          # gitignored at runtime: watchlist, ticker list, db
```

---

### Task 1: Scaffold, models, config

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `contested.toml`, `src/contested/__init__.py`, `src/contested/models.py`, `src/contested/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces (used by every later task):
  - `contested.models`: constants `BULL="bull"`, `BEAR="bear"`, `NEUTRAL="neutral"`, `MIXED="mixed"`; `utcnow() -> datetime`; `TimeWindow(start, end)` with `.hours`; `RawPost(source, post_id, author, text, ts, upvotes=0, comments=0, reposts=0, url="")`; `Event(source, post_id, author, text, ts, sentiment, intensity, engagement, tickers: tuple, url="")`; `Score(ticker, ts, window_hours, momentum, contested, bull_heat, bear_heat, n_bull, n_bear)`.
  - `contested.config`: `ConfigError`; `parse_window(spec: str) -> int` (whole hours ≥1); `SourceCfg(enabled=True, subs=[...], base_url="", board="biz")`; `ScoresCfg(window="7d", half_life_hours=48.0, l_low=1.0, l_high=7.0, contested_floor=1.0)` with `.window_hours() -> int`; `Config(sources: dict, scores, watchlist_path, db_path)`; `load_config(path=None) -> Config`; `load_watchlist(path) -> list[str]`; `resolve_config_path(explicit=None) -> Path`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "contested"
version = "0.1.0"
description = "Contested sentiment scanner for US-listed stocks"
requires-python = ">=3.11"
dependencies = ["typer>=0.12", "httpx>=0.27", "tomli-w>=1.0"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
contested = "contested.cli:app"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
*.egg-info/
.venv/
data/
.pytest_cache/
```

- [ ] **Step 3: Create `src/contested/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Create `src/contested/models.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

BULL = "bull"
BEAR = "bear"
NEUTRAL = "neutral"
MIXED = "mixed"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


@dataclass(frozen=True)
class RawPost:
    source: str
    post_id: str
    author: str
    text: str
    ts: datetime
    upvotes: int = 0
    comments: int = 0
    reposts: int = 0
    url: str = ""


@dataclass(frozen=True)
class Event:
    source: str
    post_id: str
    author: str
    text: str
    ts: datetime
    sentiment: str
    intensity: float
    engagement: float
    tickers: tuple
    url: str = ""


@dataclass(frozen=True)
class Score:
    ticker: str
    ts: datetime
    window_hours: int
    momentum: int
    contested: int
    bull_heat: float
    bear_heat: float
    n_bull: int
    n_bear: int
```

- [ ] **Step 5: Create `src/contested/config.py`**

```python
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    pass


_WINDOW_RE = re.compile(r"^(\d+)([smhdw])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(spec: str) -> int:
    m = _WINDOW_RE.match(spec.strip().lower())
    if not m:
        raise ConfigError(f"invalid duration {spec!r}; use e.g. '15m', '1h', '7d'")
    n, unit = int(m.group(1)), m.group(2)
    return max(1, n * _UNIT_SECONDS[unit])


def parse_window(spec: str) -> int:
    return max(1, int(round(parse_duration(spec) / 3600.0)))


@dataclass
class SourceCfg:
    enabled: bool = True
    subs: list = field(default_factory=lambda: ["wallstreetbets", "stocks", "investing", "Options"])
    base_url: str = ""
    board: str = "biz"


@dataclass
class ScoresCfg:
    window: str = "7d"
    half_life_hours: float = 48.0
    l_low: float = 1.0
    l_high: float = 7.0
    contested_floor: float = 1.0

    def window_hours(self) -> int:
        return parse_window(self.window)


@dataclass
class Config:
    sources: dict = field(default_factory=dict)
    scores: ScoresCfg = field(default_factory=ScoresCfg)
    watchlist_path: str = "data/watchlist.txt"
    db_path: str = "data/contested.db"


def _source_cfg(raw: dict) -> SourceCfg:
    return SourceCfg(
        enabled=bool(raw.get("enabled", True)),
        subs=list(raw.get("subs", ["wallstreetbets", "stocks", "investing", "Options"])),
        base_url=str(raw.get("base_url", "")),
        board=str(raw.get("board", "biz")),
    )


def _scores_cfg(raw: dict) -> ScoresCfg:
    cfg = ScoresCfg(
        window=str(raw.get("window", "7d")),
        half_life_hours=float(raw.get("half_life_hours", 48.0)),
        l_low=float(raw.get("l_low", 1.0)),
        l_high=float(raw.get("l_high", 7.0)),
        contested_floor=float(raw.get("contested_floor", 1.0)),
    )
    if cfg.half_life_hours <= 0:
        raise ConfigError("scores.half_life_hours must be > 0")
    if cfg.l_high <= cfg.l_low:
        raise ConfigError("scores.l_high must be > scores.l_low")
    if cfg.contested_floor < 0:
        raise ConfigError("scores.contested_floor must be >= 0")
    parse_window(cfg.window)
    return cfg


def resolve_config_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    cwd = Path.cwd() / "contested.toml"
    if cwd.is_file():
        return cwd
    return Path.home() / ".config" / "contested" / "contested.toml"


def load_config(path: str | Path | None = None) -> Config:
    p = resolve_config_path(path)
    data: dict = {}
    if p.is_file():
        with open(p, "rb") as fh:
            data = tomllib.load(fh)
    sources = {name: _source_cfg(raw) for name, raw in data.get("sources", {}).items()}
    if not sources:
        sources = {
            "reddit": SourceCfg(enabled=True),
            "x_grok": SourceCfg(enabled=True),
            "stocktwits": SourceCfg(enabled=True),
            "fourchan": SourceCfg(enabled=True),
            "facebook": SourceCfg(enabled=False),
            "instagram": SourceCfg(enabled=False),
        }
    return Config(
        sources=sources,
        scores=_scores_cfg(data.get("scores", {})),
        watchlist_path=str(data.get("watchlist", {}).get("path", "data/watchlist.txt")),
        db_path=str(data.get("db", {}).get("path", "data/contested.db")),
    )


def load_watchlist(path: str | Path) -> list:
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip().upper()
        if t and not t.startswith("#"):
            out.append(t)
    return out
```

- [ ] **Step 6: Create `contested.toml` (example/default, checked in)**

```toml
[sources.reddit]
enabled = true
# subs = ["wallstreetbets", "stocks", "investing", "Options"]

[sources.x_grok]
enabled = true
# base_url = "https://api.x.ai"   # else uses $GROK_BASE_URL

[sources.stocktwits]
enabled = true

[sources.fourchan]
enabled = true
board = "biz"

[sources.facebook]
enabled = false

[sources.instagram]
enabled = false

[scores]
window = "7d"
half_life_hours = 48.0
l_low = 1.0
l_high = 7.0
contested_floor = 1.0

[watchlist]
path = "data/watchlist.txt"

[db]
path = "data/contested.db"
```

- [ ] **Step 7: Write the failing test `tests/test_config.py`**

```python
import pytest

from contested.config import (
    ConfigError,
    load_config,
    load_watchlist,
    parse_duration,
    parse_window,
    resolve_config_path,
)


def test_parse_window_days():
    assert parse_window("7d") == 168


def test_parse_window_hours():
    assert parse_window("24h") == 24


def test_parse_window_rounds_small_up():
    assert parse_window("30m") == 1


def test_parse_window_rejects_garbage():
    with pytest.raises(ConfigError):
        parse_window("7")


def test_parse_duration_minutes():
    assert parse_duration("15m") == 900


def test_parse_duration_hours():
    assert parse_duration("1h") == 3600


def test_load_config_defaults_without_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.scores.window == "7d"
    assert cfg.scores.l_high > cfg.scores.l_low
    assert cfg.sources["facebook"].enabled is False
    assert cfg.sources["reddit"].enabled is True
    assert cfg.watchlist_path == "data/watchlist.txt"
    assert cfg.db_path == "data/contested.db"


def test_load_config_reads_file(tmp_path):
    p = tmp_path / "contested.toml"
    p.write_text(
        '[scores]\nwindow = "24h"\nl_low = 0.5\nl_high = 3.0\n'
        '[sources.x_grok]\nenabled = false\n'
        '[watchlist]\npath = "wl.txt"\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.scores.window_hours() == 24
    assert cfg.sources["x_grok"].enabled is False
    assert cfg.watchlist_path == "wl.txt"


def test_load_config_rejects_bad_band(tmp_path):
    p = tmp_path / "contested.toml"
    p.write_text('[scores]\nl_low = 5.0\nl_high = 5.0\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)


def test_load_watchlist(tmp_path):
    p = tmp_path / "wl.txt"
    p.write_text("# comment\ngme\n\namc\n", encoding="utf-8")
    assert load_watchlist(p) == ["GME", "AMC"]


def test_load_watchlist_missing(tmp_path):
    assert load_watchlist(tmp_path / "nope.txt") == []


def test_resolve_config_path_explicit(tmp_path):
    p = tmp_path / "custom.toml"
    assert resolve_config_path(p) == p
```

- [ ] **Step 8: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested'` (package not installed yet).

- [ ] **Step 9: Install the package editable so imports resolve**

Run: `python -m pip install -e .`
Expected: `Successfully installed contested-0.1.0` (and typer/httpx/tomli-w already satisfied).

- [ ] **Step 10: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: all PASS.

- [ ] **Step 11: Set repo-local git identity and commit**

```bash
git config user.name "dsh"
git config user.email "dsh@local"
git add pyproject.toml .gitignore contested.toml src/contested/__init__.py src/contested/models.py src/contested/config.py tests/test_config.py
git commit -m "feat: scaffold contested package with models and config"
```

---

### Task 2: Sentiment lexicon + classification

**Files:**
- Create: `src/contested/sentiment.py`
- Test: `tests/test_sentiment.py`

**Interfaces:**
- Consumes: nothing (pure functions).
- Produces: `BULL_TERMS: frozenset[str]`, `BEAR_TERMS: frozenset[str]`, `classify(text: str) -> str` (returns one of `"bull"`, `"bear"`, `"neutral"`, `"mixed"`), `text_intensity(text: str) -> float` (returns 1.0/2.0/3.0).

- [ ] **Step 1: Write the failing test `tests/test_sentiment.py`**

```python
from contested.sentiment import classify, text_intensity


def test_bull():
    assert classify("going LONG, to the moon") == "bull"


def test_bear():
    assert classify("I am short, this is overvalued") == "bear"


def test_mixed():
    assert classify("buy the dip or sell? long calls") == "mixed"


def test_neutral():
    assert classify("the weather is nice today") == "neutral"


def test_rip_it_vs_rip_off():
    assert classify("rip it") == "bull"
    assert classify("total rip off") == "bear"


def test_intensity_base():
    assert text_intensity("buy the dip") == 1.0


def test_intensity_emphasis_caps():
    assert text_intensity("BUY THE DIP!!!") == 2.0


def test_intensity_cap_at_3():
    assert text_intensity("I'M ALL IN, bought everything!!!") == 3.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sentiment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.sentiment'`.

- [ ] **Step 3: Write `src/contested/sentiment.py`**

```python
from __future__ import annotations

import re

BULL_TERMS: frozenset = frozenset({
    "long", "moon", "to the moon", "rip it", "buy the dip",
    "accumulate", "accumulation", "buying", "buy", "breakout",
    "upside", "rally", "bullish", "undervalued", "underrated",
    "yolo", "all in", "all-in", "diamond hands", "hodl", "pump", "green",
})

BEAR_TERMS: frozenset = frozenset({
    "short", "selling", "sell", "overvalued", "overrated", "bearish",
    "dump", "bankruptcy", "bankrupt", "delist", "fraud", "ripoff",
    "rip off", "exit", "downtrend", "downside", "red flag", "scam",
    "paper hands", "bagholder", "crash", "red",
})

_STRONG_MODALS = ("obviously", "no doubt", "everyone knows", "100%", "certain", "for sure")
_CONVICTION = (
    "all in", "all-in", "i'm in", "i am in", "bought",
    "sold everything", "selling everything", "yolo",
)


def _hit(term: str, text_lower: str) -> bool:
    if " " in term:
        return term in text_lower
    return re.search(r"\b" + re.escape(term) + r"\b", text_lower) is not None


def _count_hits(terms: frozenset, text_lower: str) -> int:
    return sum(1 for t in terms if _hit(t, text_lower))


def classify(text: str) -> str:
    tl = text.lower()
    bull = _count_hits(BULL_TERMS, tl)
    bear = _count_hits(BEAR_TERMS, tl)
    if bull > 0 and bear > 0:
        return "mixed"
    if bull > 0:
        return "bull"
    if bear > 0:
        return "bear"
    return "neutral"


def text_intensity(text: str) -> float:
    i = 1.0
    letters = [c for c in text if c.isalpha()]
    caps = (sum(1 for c in letters if c.isupper()) / len(letters)) if letters else 0.0
    tl = text.lower()
    if caps > 0.3 or text.count("!") >= 2 or any(m in tl for m in _STRONG_MODALS):
        i += 1.0
    if any(c in tl for c in _CONVICTION):
        i += 1.0
    return min(3.0, i)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sentiment.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contested/sentiment.py tests/test_sentiment.py
git commit -m "feat: add sentiment lexicon and text intensity"
```

---

### Task 3: Scorer (heat, band, momentum, contested)

**Files:**
- Create: `src/contested/scorer.py`
- Test: `tests/test_scorer.py`

**Interfaces:**
- Consumes: `contested.models` (`Event`, `Score`, `BULL`, `BEAR`, `MIXED`).
- Produces:
  - `engagement_weight(upvotes: int, comments: int, reposts: int) -> float`
  - `decay_weight(age_hours: float, half_life_hours: float) -> float`
  - `band(raw: float, l_low: float, l_high: float) -> int`
  - `score_ticker(events, ticker, now, window_hours, half_life_hours, l_low, l_high, contested_floor) -> Score`
  - `score_all(events, tickers, now, window_hours, half_life_hours, l_low, l_high, contested_floor) -> list[Score]`
  - constants `MIXED_WEIGHT=0.6`, `MAX_INTENSITY=4.0`, `REPETITION_THRESHOLD=3`

- [ ] **Step 1: Write the failing test `tests/test_scorer.py`**

```python
import math
from datetime import datetime, timedelta, timezone

from contested.models import Event
from contested.scorer import (
    band,
    decay_weight,
    engagement_weight,
    score_ticker,
)

NOW = datetime(2021, 1, 1, tzinfo=timezone.utc)


def _event(pid, author, sentiment, intensity, upvotes, ts, tickers):
    return Event(
        source="test", post_id=pid, author=author, text="x", ts=ts,
        sentiment=sentiment, intensity=intensity,
        engagement=engagement_weight(upvotes, 0, 0), tickers=tickers, url="",
    )


def test_engagement_weight():
    assert engagement_weight(9, 0, 0) == 1.0  # log10(10)


def test_decay_half_life():
    assert abs(decay_weight(48.0, 48.0) - 0.5) < 1e-9
    assert decay_weight(0.0, 48.0) == 1.0


def test_band_maps_anchors():
    # band(x, log10(1+x), anything) == 10 by construction
    x = 2.0
    assert band(x, math.log10(1 + x), math.log10(1 + x) + 2) == 10
    # top of band == 100
    assert band(10 ** 3 - 1, 0.0, 3.0) == 100
    # clamps low to 0
    assert band(0.0, 1.0, 3.0) == 0


def _gme_events():
    # 5 bull + 5 bear, distinct authors (no repetition bonus), ts=NOW (w=1)
    evs = []
    for i in range(5):
        evs.append(_event(f"b{i}", f"bull{i}", "bull", 3.0, 1000, NOW, ("GME",)))
    for i in range(5):
        evs.append(_event(f"s{i}", f"bear{i}", "bear", 3.0, 1000, NOW, ("GME",)))
    return evs


def test_gme_fixture_100_100():
    evs = _gme_events()
    # raw total = 10 events * I(3) * E(log10(1001))
    e = engagement_weight(1000, 0, 0)
    r_m = 10 * 3.0 * e
    l_high = math.log10(1 + r_m)
    s = score_ticker(evs, "GME", NOW, 168, 48.0, l_high - 1.0, l_high, 1.0)
    assert s.momentum == 100
    assert s.contested == 100
    assert s.n_bull == 5
    assert s.n_bear == 5


def test_3m_fixture_anchors_to_10():
    # small balanced: 1 bull + 1 bear, I=1, upvotes=9 (E=1), ts=NOW
    evs = [
        _event("b0", "a", "bull", 1.0, 9, NOW, ("MMM",)),
        _event("s0", "c", "bear", 1.0, 9, NOW, ("MMM",)),
    ]
    r_3m = 2.0 * 1.0 * 1.0  # 2 * I * E
    l_low = math.log10(1 + r_3m)
    l_high = l_low + 3.0
    s = score_ticker(evs, "MMM", NOW, 168, 48.0, l_low, l_high, 1.0)
    assert s.momentum == 10


def test_one_sided_contested_zero():
    evs = [
        _event("b0", "a", "bull", 3.0, 1000, NOW, ("GME",)),
        _event("b1", "b", "bull", 3.0, 1000, NOW, ("GME",)),
    ]
    s = score_ticker(evs, "GME", NOW, 168, 48.0, 0.0, 3.0, 1.0)
    assert s.contested == 0
    assert s.momentum > 0


def test_mixed_counts_both_at_0p6():
    evs = [_event("m0", "a", "mixed", 2.0, 9, NOW, ("GME",))]
    e = engagement_weight(9, 0, 0)  # 1.0
    expected = 2.0 * e * 0.6
    s = score_ticker(evs, "GME", NOW, 168, 48.0, 0.0, 5.0, 1.0)
    assert abs(s.bull_heat - expected) < 1e-9
    assert abs(s.bear_heat - expected) < 1e-9


def test_decay_halves_old_posts():
    fresh = _event("f", "a", "bull", 1.0, 9, NOW, ("GME",))
    old = _event("o", "b", "bull", 1.0, 9, NOW - timedelta(hours=48), ("GME",))
    evs = [fresh, old]
    e = engagement_weight(9, 0, 0)  # 1.0
    expected = e * 1.0 + e * 0.5  # w(fresh)=1, w(old)=0.5
    s = score_ticker(evs, "GME", NOW, 168, 48.0, 0.0, 5.0, 1.0)
    assert abs(s.bull_heat - expected) < 1e-9


def test_intensity_repetition_cap():
    # same author, 3 bull posts -> +1 repetition; base 3 -> eff 4 (capped)
    evs = [
        _event(f"b{i}", "hype", "bull", 3.0, 9, NOW, ("GME",)) for i in range(3)
    ]
    e = engagement_weight(9, 0, 0)  # 1.0
    expected = 3 * (4.0 * e)  # eff intensity 4 after repetition
    s = score_ticker(evs, "GME", NOW, 168, 48.0, 0.0, 5.0, 1.0)
    assert abs(s.bull_heat - expected) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scorer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.scorer'`.

- [ ] **Step 3: Write `src/contested/scorer.py`**

```python
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Sequence

from .models import BEAR, BULL, Event, MIXED, Score

MIXED_WEIGHT = 0.6
MAX_INTENSITY = 4.0
REPETITION_THRESHOLD = 3


def engagement_weight(upvotes: int, comments: int, reposts: int) -> float:
    return math.log10(1.0 + upvotes + 4.0 * comments + 2.0 * reposts)


def decay_weight(age_hours: float, half_life_hours: float) -> float:
    if age_hours <= 0:
        return 1.0
    return math.exp(-math.log(2.0) * age_hours / half_life_hours)


def band(raw: float, l_low: float, l_high: float) -> int:
    if raw < 0:
        raw = 0.0
    if l_high <= l_low:
        return 10
    l = math.log10(1.0 + raw)
    score = 10.0 + 90.0 * (l - l_low) / (l_high - l_low)
    return max(0, min(100, int(round(score))))


def _stances(sentiment: str) -> tuple:
    if sentiment == BULL:
        return (BULL,)
    if sentiment == BEAR:
        return (BEAR,)
    if sentiment == MIXED:
        return (BULL, BEAR)
    return ()


def score_ticker(events, ticker, now, window_hours, half_life_hours, l_low, l_high, contested_floor) -> Score:
    rel = [
        e
        for e in events
        if ticker in e.tickers
        and (now - e.ts).total_seconds() / 3600.0 <= window_hours
    ]
    stance_counts: Counter = Counter()
    for e in rel:
        for s in _stances(e.sentiment):
            stance_counts[(e.author, s)] += 1
    bull_heat = 0.0
    bear_heat = 0.0
    n_bull = 0
    n_bear = 0
    for e in rel:
        stances = _stances(e.sentiment)
        if not stances:
            continue
        age_h = (now - e.ts).total_seconds() / 3600.0
        w = decay_weight(age_h, half_life_hours)
        weight = MIXED_WEIGHT if e.sentiment == MIXED else 1.0
        for s in stances:
            rep = 1.0 if stance_counts[(e.author, s)] >= REPETITION_THRESHOLD else 0.0
            eff = min(MAX_INTENSITY, e.intensity + rep)
            bull_bear = s == BULL
            contrib = eff * e.engagement * weight * w
            if bull_bear:
                bull_heat += contrib
                n_bull += 1
            else:
                bear_heat += contrib
                n_bear += 1
    r_m = bull_heat + bear_heat
    momentum = band(r_m, l_low, l_high)
    if bull_heat < contested_floor or bear_heat < contested_floor:
        contested = 0
    else:
        balance = 2.0 * min(bull_heat, bear_heat) / r_m if r_m > 0 else 0.0
        contested = band(balance * r_m, l_low, l_high)
    return Score(
        ticker=ticker,
        ts=now,
        window_hours=window_hours,
        momentum=momentum,
        contested=contested,
        bull_heat=bull_heat,
        bear_heat=bear_heat,
        n_bull=n_bull,
        n_bear=n_bear,
    )


def score_all(events, tickers, now, window_hours, half_life_hours, l_low, l_high, contested_floor) -> list:
    return [
        score_ticker(events, t, now, window_hours, half_life_hours, l_low, l_high, contested_floor)
        for t in tickers
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scorer.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contested/scorer.py tests/test_scorer.py
git commit -m "feat: add scorer with heat, band, momentum and contested"
```

---

### Task 4: SQLite store

**Files:**
- Create: `src/contested/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `contested.models` (`Event`, `Score`, `iso`, `from_iso`, `utcnow`).
- Produces: `Store` with:
  - `Store(path)`, `.init()`, `.close()`
  - `.upsert_events(events: Sequence[Event]) -> int` (returns newly inserted count; dedupes on `(source, post_id)`)
  - `.events_in_window(now, window_hours, tickers=None) -> list[Event]`
  - `.tickers_in_window(now, window_hours) -> list[str]`
  - `.top_tickers_by_engagement(now, window_hours, limit) -> list[str]`
  - `.save_score(score: Score) -> None`
  - `.latest_scores(window_hours) -> list[Score]`
  - `.score_history(ticker, window_hours, limit=30) -> list[Score]` (oldest→newest)
  - `.record_health(source, ts, status, note) -> None`
  - `.source_health() -> list[tuple[str, datetime, str, str]]` (latest per source)

- [ ] **Step 1: Write the failing test `tests/test_store.py`**

```python
from datetime import datetime, timedelta, timezone

from contested.models import Event, Score
from contested.store import Store

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def _event(pid, author, text, ts, sentiment, engagement, tickers):
    return Event(
        source="test", post_id=pid, author=author, text=text, ts=ts,
        sentiment=sentiment, intensity=1.0, engagement=engagement,
        tickers=tickers, url="",
    )


def test_upsert_dedupes(tmp_path):
    store = Store(tmp_path / "t.db")
    store.init()
    e = _event("1", "a", "hi", NOW, "bull", 1.0, ("GME",))
    assert store.upsert_events([e]) == 1
    assert store.upsert_events([e]) == 0  # duplicate ignored
    assert store.upsert_events([_event("2", "b", "yo", NOW, "bear", 2.0, ("AMC",))]) == 1
    store.close()


def test_events_in_window_filters_time_and_ticker(tmp_path):
    store = Store(tmp_path / "t.db")
    store.init()
    store.upsert_events([
        _event("1", "a", "hi", NOW, "bull", 1.0, ("GME",)),
        _event("2", "b", "old", NOW - timedelta(hours=300), "bull", 1.0, ("GME",)),
        _event("3", "c", "amc", NOW, "bear", 1.0, ("AMC",)),
    ])
    got = store.events_in_window(NOW, 168)
    assert {e.post_id for e in got} == {"1", "3"}
    got_gme = store.events_in_window(NOW, 168, tickers=["GME"])
    assert {e.post_id for e in got_gme} == {"1"}
    assert got_gme[0].tickers == ("GME",)
    store.close()


def test_tickers_and_top_by_engagement(tmp_path):
    store = Store(tmp_path / "t.db")
    store.init()
    store.upsert_events([
        _event("1", "a", "x", NOW, "bull", 5.0, ("GME",)),
        _event("2", "b", "y", NOW, "bear", 1.0, ("AMC",)),
    ])
    assert set(store.tickers_in_window(NOW, 168)) == {"GME", "AMC"}
    assert store.top_tickers_by_engagement(NOW, 168, 5) == ["GME", "AMC"]
    store.close()


def test_score_save_latest_history(tmp_path):
    store = Store(tmp_path / "t.db")
    store.init()
    s1 = Score("GME", NOW - timedelta(hours=24), 168, 50, 40, 5.0, 4.0, 3, 2)
    s2 = Score("GME", NOW, 168, 80, 70, 9.0, 8.0, 6, 5)
    store.save_score(s1)
    store.save_score(s2)
    latest = store.latest_scores(168)
    assert latest[0].momentum == 80
    hist = store.score_history("GME", 168)
    assert [h.momentum for h in hist] == [50, 80]
    store.close()


def test_source_health_latest_per_source(tmp_path):
    store = Store(tmp_path / "t.db")
    store.init()
    store.record_health("reddit", NOW - timedelta(hours=1), "error", "boom")
    store.record_health("reddit", NOW, "ok", "")
    store.record_health("x_grok", NOW, "ok", "")
    health = dict((s, (st, note)) for s, _, st, note in store.source_health())
    assert health["reddit"] == ("ok", "")
    assert health["x_grok"] == ("ok", "")
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.store'`.

- [ ] **Step 3: Write `src/contested/store.py`**

```python
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from .models import Event, Score, from_iso, iso, utcnow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  post_id TEXT NOT NULL,
  author TEXT NOT NULL,
  text TEXT NOT NULL,
  ts TEXT NOT NULL,
  sentiment TEXT NOT NULL,
  intensity REAL NOT NULL,
  engagement REAL NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE(source, post_id)
);
CREATE TABLE IF NOT EXISTS event_tickers (
  event_id INTEGER NOT NULL,
  ticker TEXT NOT NULL,
  PRIMARY KEY(event_id, ticker)
);
CREATE TABLE IF NOT EXISTS scores (
  ticker TEXT NOT NULL,
  ts TEXT NOT NULL,
  window_hours INTEGER NOT NULL,
  momentum INTEGER NOT NULL,
  contested INTEGER NOT NULL,
  bull_heat REAL NOT NULL,
  bear_heat REAL NOT NULL,
  n_bull INTEGER NOT NULL,
  n_bear INTEGER NOT NULL,
  PRIMARY KEY(ticker, ts, window_hours)
);
CREATE TABLE IF NOT EXISTS source_health (
  source TEXT NOT NULL,
  ts TEXT NOT NULL,
  status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(source, ts)
);
"""


class Store:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row

    def init(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_events(self, events: Sequence[Event]) -> int:
        inserted = 0
        now_iso = iso(utcnow())
        with self._conn:
            for e in events:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO events "
                    "(source,post_id,author,text,ts,sentiment,intensity,engagement,url,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (e.source, e.post_id, e.author, e.text, iso(e.ts), e.sentiment,
                     e.intensity, e.engagement, e.url, now_iso),
                )
                inserted += cur.rowcount
                row = self._conn.execute(
                    "SELECT id FROM events WHERE source=? AND post_id=?",
                    (e.source, e.post_id),
                ).fetchone()
                eid = row["id"]
                for t in e.tickers:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO event_tickers (event_id,ticker) VALUES (?,?)",
                        (eid, t),
                    )
        return inserted

    def _event_row(self, row) -> Event:
        tickers = tuple(row["tickers"].split("|")) if row["tickers"] else ()
        return Event(
            source=row["source"], post_id=row["post_id"], author=row["author"],
            text=row["text"], ts=from_iso(row["ts"]), sentiment=row["sentiment"],
            intensity=row["intensity"], engagement=row["engagement"],
            tickers=tickers, url=row["url"],
        )

    def events_in_window(self, now: datetime, window_hours: int, tickers: Sequence[str] | None = None) -> list:
        start = iso(now - timedelta(hours=window_hours))
        sql = (
            "SELECT e.source,e.post_id,e.author,e.text,e.ts,e.sentiment,e.intensity,"
            "e.engagement,e.url, (SELECT group_concat(t.ticker,'|') FROM event_tickers t "
            "WHERE t.event_id=e.id) AS tickers FROM events e WHERE e.ts >= ?"
        )
        params = [start]
        if tickers:
            marks = ",".join("?" for _ in tickers)
            sql += f" AND EXISTS (SELECT 1 FROM event_tickers t WHERE t.event_id=e.id AND t.ticker IN ({marks}))"
            params.extend(tickers)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._event_row(r) for r in rows]

    def tickers_in_window(self, now: datetime, window_hours: int) -> list:
        start = iso(now - timedelta(hours=window_hours))
        rows = self._conn.execute(
            "SELECT DISTINCT t.ticker AS ticker FROM event_tickers t "
            "JOIN events e ON e.id=t.event_id WHERE e.ts >= ?",
            (start,),
        ).fetchall()
        return [r["ticker"] for r in rows]

    def top_tickers_by_engagement(self, now: datetime, window_hours: int, limit: int) -> list:
        start = iso(now - timedelta(hours=window_hours))
        rows = self._conn.execute(
            "SELECT t.ticker AS ticker, SUM(e.engagement) AS s FROM event_tickers t "
            "JOIN events e ON e.id=t.event_id WHERE e.ts >= ? "
            "GROUP BY t.ticker ORDER BY s DESC LIMIT ?",
            (start, limit),
        ).fetchall()
        return [r["ticker"] for r in rows]

    def save_score(self, score: Score) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO scores "
                "(ticker,ts,window_hours,momentum,contested,bull_heat,bear_heat,n_bull,n_bear) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (score.ticker, iso(score.ts), score.window_hours, score.momentum,
                 score.contested, score.bull_heat, score.bear_heat, score.n_bull, score.n_bear),
            )

    def latest_scores(self, window_hours: int) -> list:
        rows = self._conn.execute(
            "SELECT * FROM scores s WHERE s.window_hours=? AND s.ts=("
            "SELECT MAX(ts) FROM scores WHERE ticker=s.ticker AND window_hours=s.window_hours) "
            "ORDER BY momentum DESC, contested DESC",
            (window_hours,),
        ).fetchall()
        return [self._score_row(r) for r in rows]

    def score_history(self, ticker: str, window_hours: int, limit: int = 30) -> list:
        rows = self._conn.execute(
            "SELECT * FROM scores WHERE ticker=? AND window_hours=? ORDER BY ts DESC LIMIT ?",
            (ticker, window_hours, limit),
        ).fetchall()
        return [self._score_row(r) for r in reversed(rows)]

    def _score_row(self, r) -> Score:
        return Score(
            ticker=r["ticker"], ts=from_iso(r["ts"]), window_hours=r["window_hours"],
            momentum=r["momentum"], contested=r["contested"], bull_heat=r["bull_heat"],
            bear_heat=r["bear_heat"], n_bull=r["n_bull"], n_bear=r["n_bear"],
        )

    def record_health(self, source: str, ts: datetime, status: str, note: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO source_health (source,ts,status,note) VALUES (?,?,?,?)",
                (source, iso(ts), status, note),
            )

    def source_health(self) -> list:
        rows = self._conn.execute(
            "SELECT * FROM source_health h WHERE ts=("
            "SELECT MAX(ts) FROM source_health WHERE source=h.source)"
        ).fetchall()
        return [(r["source"], from_iso(r["ts"]), r["status"], r["note"]) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_store.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contested/store.py tests/test_store.py
git commit -m "feat: add SQLite store with dedupe, windows, scores, health"
```

---

### Task 5: Normalizer (ticker extraction + RawPost→Event)

**Files:**
- Create: `src/contested/normalizer.py`
- Test: `tests/test_normalizer.py`

**Interfaces:**
- Consumes: `contested.models` (`RawPost`, `Event`); `contested.sentiment` (`classify`, `text_intensity`); `contested.scorer` (`engagement_weight`).
- Produces:
  - `extract_tickers(text: str, ticker_set: frozenset) -> tuple[str, ...]` (ordered, unique, US-validated)
  - `normalize_posts(raws: Sequence[RawPost], ticker_set: frozenset) -> list[Event]` (drops posts with no US ticker)

- [ ] **Step 1: Write the failing test `tests/test_normalizer.py`**

```python
from datetime import datetime, timezone

from contested.models import RawPost
from contested.normalizer import extract_tickers, normalize_posts

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
SET = frozenset({"GME", "AMC", "MMM", "GOOGL"})


def test_extract_cashtag():
    assert extract_tickers("going long $GME", SET) == ("GME",)


def test_extract_bare_mention():
    assert extract_tickers("GME is ripping", SET) == ("GME",)


def test_extract_multiple_ordered_unique():
    assert extract_tickers("$GME then AMC and $GME again", SET) == ("GME", "AMC")


def test_drops_non_us():
    assert extract_tickers("$TSM and $700", SET) == ()


def test_bare_short_word_ignored():
    # len < 3 bare mention should not match
    assert extract_tickers("AMC MMM GOOGL", SET) == ("AMC", "MMM", "GOOGL")


def test_word_boundary():
    # substring of a longer word should not match
    assert extract_tickers("the gamestop store", SET) == ()


def test_normalize_drops_no_ticker():
    r = RawPost("t", "1", "a", "no ticker here", NOW)
    assert normalize_posts([r], SET) == []


def test_normalize_classifies_and_weights():
    r = RawPost("t", "1", "a", "LONG $GME to the moon", NOW, upvotes=9)
    evs = normalize_posts([r], SET)
    assert len(evs) == 1
    e = evs[0]
    assert e.tickers == ("GME",)
    assert e.sentiment == "bull"
    assert e.engagement == 1.0  # log10(1+9)
    assert e.intensity >= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_normalizer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.normalizer'`.

- [ ] **Step 3: Write `src/contested/normalizer.py`**

```python
from __future__ import annotations

import re
from typing import Sequence

from .models import Event, RawPost
from .scorer import engagement_weight
from .sentiment import classify, text_intensity

_CASE_RE = re.compile(r"\$([A-Za-z]{1,5})\b")
_WORD_RE = re.compile(r"\b[A-Za-z]{3,5}\b")


def extract_tickers(text: str, ticker_set: frozenset) -> tuple:
    found = []
    seen = set()
    for m in _CASE_RE.finditer(text):
        t = m.group(1).upper()
        if t in ticker_set and t not in seen:
            seen.add(t)
            found.append(t)
    for m in _WORD_RE.finditer(text):
        t = m.group(0).upper()
        if t in ticker_set and t not in seen:
            seen.add(t)
            found.append(t)
    return tuple(found)


def normalize_posts(raws: Sequence[RawPost], ticker_set: frozenset) -> list:
    out = []
    for r in raws:
        tickers = extract_tickers(r.text, ticker_set)
        if not tickers:
            continue
        out.append(
            Event(
                source=r.source,
                post_id=r.post_id,
                author=r.author,
                text=r.text,
                ts=r.ts,
                sentiment=classify(r.text),
                intensity=text_intensity(r.text),
                engagement=engagement_weight(r.upvotes, r.comments, r.reposts),
                tickers=tickers,
                url=r.url,
            )
        )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_normalizer.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contested/normalizer.py tests/test_normalizer.py
git commit -m "feat: add normalizer with US ticker extraction and event building"
```

---

### Task 6: Ticker list (load + NASDAQ download)

**Files:**
- Create: `src/contested/tickerlist.py`
- Create: `tests/fixtures/tickers.txt`
- Test: `tests/test_tickerlist.py`

**Interfaces:**
- Consumes: `httpx` (for download).
- Produces:
  - `NASDAQ_LISTED_URL`, `OTHER_LISTED_URL` (str)
  - `load_ticker_set(path: str | Path) -> frozenset[str]`
  - `download_ticker_list(dest: str | Path, client: httpx.Client | None = None) -> frozenset[str]`

- [ ] **Step 1: Create fixture `tests/fixtures/tickers.txt`**

```
GME
AMC
MMM
GOOGL
NVDA
TSLA
AAPL
MSFT
```

- [ ] **Step 2: Write the failing test `tests/test_tickerlist.py`**

```python
import httpx

from contested.tickerlist import download_ticker_list, load_ticker_set


def test_load_ticker_set(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("# comment\nGME\n\namc\nMMM\n", encoding="utf-8")
    assert load_ticker_set(p) == frozenset({"GME", "AMC", "MMM"})


def test_download_parses_nasdaq(tmp_path):
    listed = "Symbol\tCompany Name\nGME\tGameStop\nMMM\t3M\n"
    other = "Symbol\tCompany Name\nAAPL\tApple\n"
    def handler(request: httpx.Request) -> httpx.Response:
        if "nasdaqlisted" in request.url.path:
            return httpx.Response(200, text=listed)
        return httpx.Response(200, text=other)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    dest = tmp_path / "tickers_us.txt"
    got = download_ticker_list(dest, client=client)
    assert got == frozenset({"GME", "MMM", "AAPL"})
    assert dest.is_file()


def test_download_failure_raises(tmp_path):
    import pytest
    from contested.tickerlist import TickerListError
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(TickerListError):
        download_ticker_list(tmp_path / "t.txt", client=client)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_tickerlist.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.tickerlist'`.

- [ ] **Step 4: Write `src/contested/tickerlist.py`**

```python
from __future__ import annotations

import re
from pathlib import Path

import httpx

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_TOK = re.compile(r"^[A-Z][A-Z.]{1,9}$")


class TickerListError(Exception):
    pass


def load_ticker_set(path: str | Path) -> frozenset:
    p = Path(path)
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip().upper()
        if t and not t.startswith("#") and _TOK.match(t):
            out.add(t)
    return frozenset(out)


def _parse_first_column(text: str) -> set:
    out = set()
    for line in text.splitlines():
        first = line.split("\t", 1)[0].strip().upper()
        if first and first != "SYMBOL" and _TOK.match(first):
            out.add(first)
    return out


def download_ticker_list(dest: str | Path, client: httpx.Client | None = None) -> frozenset:
    own = client is None
    if own:
        client = httpx.Client(timeout=30.0)
    try:
        union = set()
        for url in (NASDAQ_LISTED_URL, OTHER_LISTED_URL):
            resp = client.get(url)
            if resp.status_code != 200:
                raise TickerListError(f"HTTP {resp.status_code} fetching {url}")
            union |= _parse_first_column(resp.text)
        if not union:
            raise TickerListError("ticker list empty after parse")
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_text("\n".join(sorted(union)) + "\n", encoding="utf-8")
        return frozenset(union)
    finally:
        if own:
            client.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_tickerlist.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/contested/tickerlist.py tests/test_tickerlist.py tests/fixtures/tickers.txt
git commit -m "feat: add US ticker list loader and NASDAQ downloader"
```

---

### Task 7: Source base (protocol, error, http helper)

**Files:**
- Create: `src/contested/sources/__init__.py` (placeholder, filled in Task 11)
- Create: `src/contested/sources/base.py`
- Test: `tests/test_sources_base.py`

**Interfaces:**
- Consumes: `httpx`; `contested.models` (`TimeWindow`).
- Produces:
  - `SourceError(Exception)`
  - `Source` protocol (`.name: str`, `.fetch(tickers: list[str], window: TimeWindow) -> list[RawPost]`)
  - `http_get_json(url: str, client: httpx.Client, params=None, headers=None, retries: int = 2, backoff: float = 0.0) -> dict` (raises `SourceError` after retries; 5xx/429 retried, other 4xx raised immediately)
  - `http_post_json(url, client, payload, headers, retries=2, backoff=0.0) -> dict`

Note: create `sources/__init__.py` as an empty file in this task so the package imports; its contents (`build_sources`) are added in Task 11.

- [ ] **Step 1: Create `src/contested/sources/__init__.py` (empty placeholder)**

```python
# Registry (build_sources) is added in Task 11.
```

- [ ] **Step 2: Write the failing test `tests/test_sources_base.py`**

```python
import httpx
import pytest

from contested.sources.base import SourceError, http_get_json


def test_get_json_success():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"a": 1})))
    assert http_get_json("http://x/y", client) == {"a": 1}


def test_get_json_retries_then_succeeds():
    calls = {"n": 0}
    def handler(r):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert http_get_json("http://x", client, backoff=0.0) == {"ok": True}
    assert calls["n"] == 2


def test_get_json_exhausts_retries():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(SourceError):
        http_get_json("http://x", client, retries=2, backoff=0.0)


def test_get_json_4xx_no_retry():
    calls = {"n": 0}
    def handler(r):
        calls["n"] += 1
        return httpx.Response(404)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(SourceError):
        http_get_json("http://x", client, retries=3, backoff=0.0)
    assert calls["n"] == 1  # no retry on 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_sources_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.sources.base'`.

- [ ] **Step 4: Write `src/contested/sources/base.py`**

```python
from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

import httpx

from ..models import RawPost, TimeWindow


class SourceError(Exception):
    pass


@runtime_checkable
class Source(Protocol):
    name: str

    def fetch(self, tickers: list, window: TimeWindow) -> list:
        ...


def _request(client: httpx.Client, method: str, url: str, retries: int, backoff: float, **kwargs) -> dict:
    last = None
    for attempt in range(retries + 1):
        resp = client.request(method, url, **kwargs)
        if resp.status_code == 200:
            return resp.json()
        last = f"HTTP {resp.status_code}"
        if 400 <= resp.status_code < 500 and resp.status_code != 429:
            break  # client error: don't retry
        if attempt < retries:
            time.sleep(backoff)
    raise SourceError(f"{method} {url} failed: {last}")


def http_get_json(url, client, params=None, headers=None, retries=2, backoff=0.0) -> dict:
    return _request(client, "GET", url, retries, backoff, params=params, headers=headers)


def http_post_json(url, client, payload=None, headers=None, retries=2, backoff=0.0) -> dict:
    return _request(client, "POST", url, retries, backoff, json=payload, headers=headers)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_sources_base.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/contested/sources/__init__.py src/contested/sources/base.py tests/test_sources_base.py
git commit -m "feat: add source protocol, SourceError, and retried http json helpers"
```

---

### Task 8: Reddit source

**Files:**
- Create: `src/contested/sources/reddit.py`
- Test: `tests/test_sources_reddit.py`

**Interfaces:**
- Consumes: `contested.sources.base` (`http_get_json`, `SourceError`); `contested.models` (`RawPost`, `TimeWindow`); `httpx`.
- Produces: `RedditSource(client=None, client_id="", client_secret="", subs=("wallstreetbets","stocks","investing","Options"), user_agent="contested/0.1 (+local)")` with `.name == "reddit"` and `.fetch(tickers, window) -> list[RawPost]`.
  - `fetch([], window)` = market mode: poll `r/{sub}/new.json?limit=100` per sub, filter `created_utc` into window.
  - `fetch([t...], window)` = per-ticker: `search.json?q=$T&sort=new&limit=100`, filter into window.

- [ ] **Step 1: Write the failing test `tests/test_sources_reddit.py`**

```python
import httpx
from datetime import datetime, timezone

from contested.models import TimeWindow
from contested.sources.reddit import RedditSource

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
WINDOW = TimeWindow(start=NOW.replace(hour=10), end=NOW)
# created_utc ~ 2026-10-26 11:00 UTC
TS = int(NOW.replace(hour=11).timestamp())


def _body(children):
    return {"data": {"children": children}}


def _child(id_, author, title, selftext, score, comments, created, perm):
    return {"data": {"id": id_, "author": author, "title": title,
                     "selftext": selftext, "score": score,
                     "num_comments": comments, "created_utc": created,
                     "permalink": perm}}


def test_market_mode_parses_subs():
    def handler(r):
        assert "/r/wallstreetbets/new.json" in str(r.url)
        return httpx.Response(200, json=_body([
            _child("a1", "u1", "LONG $GME", "to the moon", 500, 40, TS, "/r/wsb/comments/a1"),
            _child("a2", "u2", "old post", "x", 10, 1, TS - 9999999, "/r/wsb/comments/a2"),
        ]))
    client = httpx.Client(transport=httpx.MockTransport(handler))
    src = RedditSource(client=client, subs=("wallstreetbets",))
    posts = src.fetch([], WINDOW)
    assert len(posts) == 1  # old post filtered out of window
    p = posts[0]
    assert p.source == "reddit"
    assert p.post_id == "a1"
    assert p.upvotes == 500
    assert p.comments == 40
    assert "$GME" in p.text


def test_per_ticker_mode_uses_search():
    seen = []
    def handler(r):
        seen.append(str(r.url))
        return httpx.Response(200, json=_body([
            _child("b1", "u3", "GME dip", "buy", 100, 5, TS, "/r/wsb/comments/b1"),
        ]))
    client = httpx.Client(transport=httpx.MockTransport(handler))
    src = RedditSource(client=client, subs=("wallstreetbets",))
    posts = src.fetch(["GME"], WINDOW)
    assert any("search.json" in u and "%24GME" in u for u in seen)
    assert len(posts) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sources_reddit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.sources.reddit'`.

- [ ] **Step 3: Write `src/contested/sources/reddit.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import RawPost, TimeWindow
from .base import http_get_json

_UA_DEFAULT = "contested/0.1 (local sentiment scanner)"


class RedditSource:
    name = "reddit"

    def __init__(self, client=None, client_id="", client_secret="",
                 subs=("wallstreetbets", "stocks", "investing", "Options"),
                 user_agent=_UA_DEFAULT):
        self._client = client or httpx.Client(timeout=20.0)
        self._own_client = client is None
        self._client_id = client_id
        self._client_secret = client_secret
        self._subs = tuple(subs)
        self._ua = user_agent
        self._token = None

    def _headers(self):
        h = {"User-Agent": self._ua, "Accept": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _maybe_token(self):
        if self._token is not None or not (self._client_id and self._client_secret):
            return
        try:
            resp = self._client.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(self._client_id, self._client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self._ua},
            )
            if resp.status_code == 200:
                self._token = resp.json().get("access_token")
        except Exception:
            self._token = None

    def _children(self, url):
        data = http_get_json(url, self._client, headers=self._headers())
        return data.get("data", {}).get("children", [])

    def _to_post(self, c, source_id_prefix=""):
        d = c.get("data", {})
        created = d.get("created_utc")
        if created is None:
            return None
        ts = datetime.fromtimestamp(created, tz=timezone.utc)
        text = (d.get("title", "") + " " + d.get("selftext", "")).strip()
        if not text:
            return None
        return RawPost(
            source=self.name,
            post_id=source_id_prefix + str(d.get("id")),
            author=str(d.get("author", "")),
            text=text,
            ts=ts,
            upvotes=int(d.get("score", 0) or 0),
            comments=int(d.get("num_comments", 0) or 0),
            reposts=0,
            url="https://www.reddit.com" + d.get("permalink", ""),
        )

    def _in_window(self, post, window):
        return window.start <= post.ts <= window.end

    def fetch(self, tickers, window: TimeWindow):
        self._maybe_token()
        posts = []
        if tickers:
            for t in tickers:
                url = f"https://www.reddit.com/search.json?q=%24{t}&sort=new&limit=100"
                for c in self._children(url):
                    p = self._to_post(c)
                    if p and self._in_window(p, window):
                        posts.append(p)
        else:
            for sub in self._subs:
                url = f"https://www.reddit.com/r/{sub}/new.json?limit=100"
                for c in self._children(url):
                    p = self._to_post(c)
                    if p and self._in_window(p, window):
                        posts.append(p)
        return posts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sources_reddit.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contested/sources/reddit.py tests/test_sources_reddit.py
git commit -m "feat: add reddit source with market and per-ticker modes"
```

---

### Task 9: Stocktwits + 4chan sources

**Files:**
- Create: `src/contested/sources/stocktwits.py`
- Create: `src/contested/sources/fourchan.py`
- Test: `tests/test_sources_stocktwits.py`, `tests/test_sources_fourchan.py`

**Interfaces:**
- Consumes: `contested.sources.base` (`http_get_json`, `SourceError`); `contested.models` (`RawPost`, `TimeWindow`); `httpx`.
- Produces:
  - `StocktwitsSource(client=None)` `.name == "stocktwits"` `.fetch(tickers, window)`. Market (`[]`): `streams/message.json?limit=200`. Per-ticker: `streams/symbol/{T}.json?limit=200`.
  - `FourChanSource(client=None, board="biz")` `.name == "fourchan"` `.fetch(tickers, window)` — always polls `a.4cdn.org/{board}/catalog.json` (tickers are extracted later by the normalizer).

- [ ] **Step 1: Write the failing test `tests/test_sources_stocktwits.py`**

```python
import httpx
from datetime import datetime, timezone

from contested.models import TimeWindow
from contested.sources.stocktwits import StocktwitsSource

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
WINDOW = TimeWindow(start=NOW.replace(hour=10), end=NOW)
TS = "2026-10-26T11:00:00Z"


def _msg(mid, body, created, user, like, replies, retweets, symbols):
    return {"id": mid, "body": body, "created_at": created,
            "user": {"username": user},
            "reactions": {"like": like},
            "replies": replies, "retweets": retweets,
            "symbols": symbols}


def test_market_mode():
    def handler(r):
        assert "/streams/message.json" in str(r.url)
        return httpx.Response(200, json={"messages": [
            _msg("1", "long $GME", TS, "u1", 10, 2, 1, [{"symbol": "GME"}]),
            _msg("2", "old", "2020-01-01T00:00:00Z", "u2", 1, 0, 0, [{"symbol": "AMC"}]),
        ]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    posts = StocktwitsSource(client=client).fetch([], WINDOW)
    assert len(posts) == 1
    assert posts[0].upvotes == 10
    assert posts[0].reposts == 1


def test_per_ticker_mode():
    seen = []
    def handler(r):
        seen.append(str(r.url))
        return httpx.Response(200, json={"messages": [
            _msg("9", "GME dip buy", TS, "u9", 5, 0, 0, [{"symbol": "GME"}]),
        ]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    posts = StocktwitsSource(client=client).fetch(["GME"], WINDOW)
    assert any("/symbol/GME.json" in u for u in seen)
    assert len(posts) == 1
```

- [ ] **Step 2: Write the failing test `tests/test_sources_fourchan.py`**

```python
import httpx
from datetime import datetime, timezone

from contested.models import TimeWindow
from contested.sources.fourchan import FourChanSource

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
WINDOW = TimeWindow(start=NOW.replace(hour=10), end=NOW)
TS_EPOCH = int(NOW.replace(hour=11).timestamp())


def test_catalog_parsed():
    def handler(r):
        assert "/biz/catalog.json" in str(r.url)
        return httpx.Response(200, json=[
            {"No": 111, "sub": "GME thread", "com": "to the moon",
             "cap": 30, "replies": 12, "last_time": TS_EPOCH},
            {"No": 222, "sub": "old", "com": "x",
             "cap": 1, "replies": 0, "last_time": TS_EPOCH - 9999999},
        ])
    client = httpx.Client(transport=httpx.MockTransport(handler))
    posts = FourChanSource(client=client).fetch([], WINDOW)
    assert len(posts) == 1  # old thread filtered out
    assert posts[0].post_id == "111"
    assert posts[0].upvotes == 30
    assert posts[0].comments == 12
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_sources_stocktwits.py tests/test_sources_fourchan.py -v`
Expected: FAIL — `ModuleNotFoundError` for both modules.

- [ ] **Step 4: Write `src/contested/sources/stocktwits.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import RawPost, TimeWindow
from .base import http_get_json


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class StocktwitsSource:
    name = "stocktwits"

    def __init__(self, client=None):
        self._client = client or httpx.Client(timeout=20.0)

    def _messages(self, url):
        data = http_get_json(url, self._client)
        return data.get("messages", [])

    def _to_post(self, m):
        created = m.get("created_at")
        if not created:
            return None
        try:
            ts = _parse_ts(created)
        except ValueError:
            return None
        body = m.get("body", "")
        if not body:
            return None
        react = m.get("reactions", {}) or {}
        return RawPost(
            source=self.name,
            post_id=str(m.get("id")),
            author=str((m.get("user") or {}).get("username", "")),
            text=body,
            ts=ts,
            upvotes=int(react.get("like", 0) or 0),
            comments=int(m.get("replies", 0) or 0),
            reposts=int(m.get("retweets", 0) or 0),
            url="https://stocktwits.com/message/" + str(m.get("id", "")),
        )

    def _in_window(self, post, window):
        return window.start <= post.ts <= window.end

    def fetch(self, tickers, window: TimeWindow):
        posts = []
        if tickers:
            for t in tickers:
                url = f"https://api.stocktwits.com/api/2/streams/symbol/{t}.json?limit=200"
                for m in self._messages(url):
                    p = self._to_post(m)
                    if p and self._in_window(p, window):
                        posts.append(p)
        else:
            url = "https://api.stocktwits.com/api/2/streams/message.json?limit=200"
            for m in self._messages(url):
                p = self._to_post(m)
                if p and self._in_window(p, window):
                    posts.append(p)
        return posts
```

- [ ] **Step 5: Write `src/contested/sources/fourchan.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import RawPost, TimeWindow
from .base import http_get_json


class FourChanSource:
    name = "fourchan"

    def __init__(self, client=None, board="biz"):
        self._client = client or httpx.Client(timeout=20.0)
        self._board = board

    def fetch(self, tickers, window: TimeWindow):
        url = f"https://a.4cdn.org/{self._board}/catalog.json"
        threads = http_get_json(url, self._client)
        posts = []
        for t in threads:
            last = t.get("last_time")
            if last is None:
                continue
            ts = datetime.fromtimestamp(last, tz=timezone.utc)
            if not (window.start <= ts <= window.end):
                continue
            text = ((t.get("sub", "") or "") + " " + (t.get("com", "") or "")).strip()
            if not text:
                continue
            posts.append(RawPost(
                source=self.name,
                post_id=str(t.get("No")),
                author="4anon",
                text=text,
                ts=ts,
                upvotes=int(t.get("cap", 0) or 0),
                comments=int(t.get("replies", 0) or 0),
                reposts=0,
                url=f"https://boards.4chan.org/{self._board}/thread/{t.get('No')}",
            ))
        return posts
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_sources_stocktwits.py tests/test_sources_fourchan.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/contested/sources/stocktwits.py src/contested/sources/fourchan.py tests/test_sources_stocktwits.py tests/test_sources_fourchan.py
git commit -m "feat: add stocktwits and 4chan sources"
```

---

### Task 10: X (Grok) source

**Files:**
- Create: `src/contested/sources/x_grok.py`
- Test: `tests/test_sources_x_grok.py`

**Interfaces:**
- Consumes: `contested.sources.base` (`http_post_json`, `SourceError`); `contested.models` (`RawPost`, `TimeWindow`); `httpx`.
- Produces: `XGrokSource(client=None, base_url="", api_key="")` `.name == "x_grok"` `.fetch(tickers, window) -> list[RawPost]` — per-ticker only (posts a `x_search` per `$CASHTAG`).

- [ ] **Step 1: Write the failing test `tests/test_sources_x_grok.py`**

```python
import httpx
from datetime import datetime, timezone

from contested.models import TimeWindow
from contested.sources.x_grok import XGrokSource

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
WINDOW = TimeWindow(start=NOW.replace(hour=10), end=NOW)
TS = "2026-10-26T11:00:00Z"


def _resp(rows):
    return {"results": rows}


def _row(rid, text, user, created, likes=0, rts=0, replies=0):
    return {"post": {"id": rid, "contents": {"text": text}, "user": {"username": user},
                     "created_at": created, "like_count": likes, "retweet_count": rts,
                     "reply_count": replies, "url": f"https://x.com/{user}/status/{rid}"}}


def test_fetch_posts_per_cashtag():
    seen = []
    def handler(r):
        seen.append((str(r.url), r.read()))
        return httpx.Response(200, json=_resp([
            _row("1", "long $GME", "u1", TS, likes=9, rts=2, replies=4),
        ]))
    client = httpx.Client(transport=httpx.MockTransport(handler))
    src = XGrokSource(client=client, base_url="https://api.x.ai", api_key="k")
    posts = src.fetch(["GME"], WINDOW)
    assert len(posts) == 1
    assert posts[0].upvotes == 9
    assert posts[0].reposts == 2
    url = seen[0][0]
    assert url == "https://api.x.ai/v1/x_search"
    body = seen[0][1]
    assert b"GME" in body


def test_fetch_empty_tickers_returns_empty():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    src = XGrokSource(client=client, base_url="https://api.x.ai", api_key="k")
    assert src.fetch([], WINDOW) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sources_x_grok.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.sources.x_grok'`.

- [ ] **Step 3: Write `src/contested/sources/x_grok.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import RawPost, TimeWindow
from .base import SourceError, http_post_json


def _parse_ts(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class XGrokSource:
    name = "x_grok"

    def __init__(self, client=None, base_url="", api_key=""):
        self._client = client or httpx.Client(timeout=30.0)
        self._base_url = (base_url or "https://api.x.ai").rstrip("/")
        self._api_key = api_key

    def _headers(self):
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _search(self, ticker, window):
        payload = {
            "query": f"${ticker}",
            "from_date": window.start.date().isoformat(),
            "to_date": window.end.date().isoformat(),
        }
        data = http_post_json(f"{self._base_url}/v1/x_search", self._client,
                              payload=payload, headers=self._headers())
        rows = data.get("results") or data.get("data") or []
        posts = []
        for i, row in enumerate(rows):
            post = row.get("post", row)
            contents = post.get("contents", {}) or {}
            text = contents.get("text") or post.get("text") or row.get("text") or ""
            if not text:
                continue
            ts = _parse_ts(post.get("created_at") or row.get("created_at"))
            if ts is None:
                continue
            if not (window.start <= ts <= window.end):
                continue
            user = (post.get("user") or {})
            posts.append(RawPost(
                source=self.name,
                post_id=str(post.get("id") or post.get("rest_id") or f"row{i}"),
                author=str(user.get("username", "") if isinstance(user, dict) else user),
                text=text,
                ts=ts,
                upvotes=int(post.get("like_count") or post.get("likes") or 0),
                comments=int(post.get("reply_count") or 0),
                reposts=int(post.get("retweet_count") or 0),
                url=str(post.get("url") or ""),
            ))
        return posts

    def fetch(self, tickers, window: TimeWindow):
        posts = []
        for t in tickers:
            posts.extend(self._search(t, window))
        return posts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sources_x_grok.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contested/sources/x_grok.py tests/test_sources_x_grok.py
git commit -m "feat: add x_grok source posting per-cashtag x_search"
```

---

### Task 11: FB/IG stubs + registry (build_sources)

**Files:**
- Create: `src/contested/sources/facebook.py`
- Create: `src/contested/sources/instagram.py`
- Modify: `src/contested/sources/__init__.py` (replace placeholder with registry)
- Test: `tests/test_sources_stubs.py`, `tests/test_sources_registry.py`

**Interfaces:**
- Consumes: all source classes (Tasks 8–10); `contested.config` (`Config`, `ConfigError`); `contested.sources.base` (`SourceError`).
- Produces:
  - `FacebookSource()` `.name == "facebook"`, `.fetch(...)` raises `SourceError`.
  - `InstagramSource()` `.name == "instagram"`, `.fetch(...)` raises `SourceError`.
  - `build_sources(cfg: Config) -> dict[str, Source]` — returns only enabled sources; raises `ConfigError` if `x_grok` enabled without `GROK_BASE_URL`/`GROK_API_KEY`, or for an unknown source name.

- [ ] **Step 1: Write the failing test `tests/test_sources_stubs.py`**

```python
import pytest
from datetime import datetime, timezone

from contested.models import TimeWindow
from contested.sources.base import SourceError
from contested.sources.facebook import FacebookSource
from contested.sources.instagram import InstagramSource

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
W = TimeWindow(NOW, NOW)


def test_facebook_stub_raises():
    with pytest.raises(SourceError):
        FacebookSource().fetch(["GME"], W)


def test_instagram_stub_raises():
    with pytest.raises(SourceError):
        InstagramSource().fetch(["GME"], W)
```

- [ ] **Step 2: Write the failing test `tests/test_sources_registry.py`**

```python
import pytest

from contested.config import Config, ConfigError, ScoresCfg, SourceCfg
from contested.sources import build_sources


def _cfg(**overrides):
    sources = {
        "reddit": SourceCfg(enabled=True),
        "x_grok": SourceCfg(enabled=True),
        "stocktwits": SourceCfg(enabled=True),
        "fourchan": SourceCfg(enabled=True),
        "facebook": SourceCfg(enabled=False),
        "instagram": SourceCfg(enabled=False),
    }
    sources.update(overrides)
    return Config(sources=sources, scores=ScoresCfg())


def test_build_includes_only_enabled(monkeypatch):
    monkeypatch.setenv("GROK_BASE_URL", "https://api.x.ai")
    monkeypatch.setenv("GROK_API_KEY", "k")
    built = build_sources(_cfg())
    assert set(built) == {"reddit", "x_grok", "stocktwits", "fourchan"}


def test_x_grok_requires_env(monkeypatch):
    monkeypatch.delenv("GROK_BASE_URL", raising=False)
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        build_sources(_cfg())


def test_unknown_source_rejected():
    with pytest.raises(ConfigError):
        build_sources(_cfg(bogus=SourceCfg(enabled=True)))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_sources_stubs.py tests/test_sources_registry.py -v`
Expected: FAIL — modules/`build_sources` not defined.

- [ ] **Step 4: Write `src/contested/sources/facebook.py` and `instagram.py`**

`facebook.py`:
```python
from __future__ import annotations

from ..models import RawPost, TimeWindow
from .base import SourceError


class FacebookSource:
    name = "facebook"

    def fetch(self, tickers, window: TimeWindow) -> list:
        raise SourceError("facebook: no access path in v1 (adapter stub)")
```

`instagram.py`:
```python
from __future__ import annotations

from ..models import RawPost, TimeWindow
from .base import SourceError


class InstagramSource:
    name = "instagram"

    def fetch(self, tickers, window: TimeWindow) -> list:
        raise SourceError("instagram: no access path in v1 (adapter stub)")
```

- [ ] **Step 5: Replace `src/contested/sources/__init__.py` with the registry**

```python
from __future__ import annotations

import os

from ..config import Config, ConfigError
from .base import Source, SourceError
from .facebook import FacebookSource
from .fourchan import FourChanSource
from .instagram import InstagramSource
from .reddit import RedditSource
from .stocktwits import StocktwitsSource
from .x_grok import XGrokSource

__all__ = ["build_sources", "Source", "SourceError"]


def build_sources(cfg: Config) -> dict:
    env = os.environ
    out = {}
    for name, scfg in cfg.sources.items():
        if not scfg.enabled:
            continue
        if name == "reddit":
            out[name] = RedditSource(
                client_id=env.get("REDDIT_CLIENT_ID", ""),
                client_secret=env.get("REDDIT_CLIENT_SECRET", ""),
                subs=tuple(scfg.subs),
            )
        elif name == "x_grok":
            base_url = scfg.base_url or env.get("GROK_BASE_URL", "")
            api_key = env.get("GROK_API_KEY", "")
            if not base_url or not api_key:
                raise ConfigError(
                    "x_grok is enabled but GROK_BASE_URL and GROK_API_KEY env vars are required"
                )
            out[name] = XGrokSource(base_url=base_url, api_key=api_key)
        elif name == "stocktwits":
            out[name] = StocktwitsSource()
        elif name == "fourchan":
            out[name] = FourChanSource(board=scfg.board)
        elif name == "facebook":
            out[name] = FacebookSource()
        elif name == "instagram":
            out[name] = InstagramSource()
        else:
            raise ConfigError(f"unknown source {name!r} in config")
    return out
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_sources_stubs.py tests/test_sources_registry.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/contested/sources/facebook.py src/contested/sources/instagram.py src/contested/sources/__init__.py tests/test_sources_stubs.py tests/test_sources_registry.py
git commit -m "feat: add fb/ig stubs and source registry with env validation"
```

---

### Task 12: Collector (watch.run_cycle)

**Files:**
- Create: `src/contested/watch.py`
- Test: `tests/test_watch.py`
- Test: `tests/conftest.py` (shared fakes, if not already present)

**Interfaces:**
- Consumes: `contested.store` (`Store`); `contested.normalizer` (`normalize_posts`); `contested.models` (`TimeWindow`, `utcnow`); `contested.config` (`Config`); `contested.sources.base` (`SourceError`); `contested.scorer` (not directly).
- Produces:
  - `CycleReport` dataclass: `.inserted: int`, `.per_source: dict[str, int]`, `.errors: dict[str, str]`
  - `run_cycle(sources: dict, store: Store, cfg: Config, ticker_set: frozenset, mode: str, watchlist: list, now=None) -> CycleReport`
    - `mode == "market"`: cheap sources (`reddit`,`stocktwits`,`fourchan`) fetched with `[]` (market-wide); then `top_tickers_by_engagement(…, 50)` ∪ watchlist fed to per-ticker sources (`x_grok`,`facebook`,`instagram`).
    - `mode == "watch"`: every enabled source fetched with the watchlist tickers.
    - Each source failure is captured in `report.errors` + `store.record_health(…,"error",…)`; the cycle never aborts on one source.

- [ ] **Step 1: Create `tests/conftest.py` (shared fixtures)**

```python
import pytest
from datetime import datetime, timezone

from contested.models import RawPost, TimeWindow

# Test "now": real current time truncated to seconds. Dynamic so the CLI/e2e
# tests (which scan with the real utcnow()) keep passing at any future date;
# the store round-trips timestamps with second precision.
NOW = datetime.now(timezone.utc).replace(microsecond=0)


class FakeSource:
    def __init__(self, name, posts=None, error=None):
        self.name = name
        self._posts = posts or []
        self._error = error
        self.last_tickers = None

    def fetch(self, tickers, window: TimeWindow):
        self.last_tickers = list(tickers)
        if self._error:
            raise self._error
        return list(self._posts)


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def ticker_set():
    return frozenset({"GME", "AMC", "MMM"})
```

- [ ] **Step 2: Write the failing test `tests/test_watch.py`**

```python
from datetime import timedelta, timezone

from contested.config import Config, ScoresCfg, SourceCfg
from contested.models import RawPost
from contested.sources.base import SourceError
from contested.store import Store
from contested.watch import run_cycle
from conftest import FakeSource, NOW


def _cfg():
    sources = {
        "reddit": SourceCfg(enabled=True),
        "x_grok": SourceCfg(enabled=True),
        "stocktwits": SourceCfg(enabled=True),
        "fourchan": SourceCfg(enabled=True),
    }
    return Config(sources=sources, scores=ScoresCfg(window="7d"))


def _post(pid, text):
    return RawPost("reddit", pid, "a", text, NOW)


def test_watch_mode_fetches_watchlist(tmp_path):
    store = Store(tmp_path / "t.db"); store.init()
    reddit = FakeSource("reddit", [_post("1", "long $GME")])
    xg = FakeSource("x_grok", [_post("2", "$GME sell")])
    report = run_cycle(
        {"reddit": reddit, "x_grok": xg}, store, _cfg(),
        frozenset({"GME"}), "watch", ["GME"], now=NOW,
    )
    assert report.inserted == 2
    assert reddit.last_tickers == ["GME"]
    assert xg.last_tickers == ["GME"]
    assert report.errors == {}
    health = {s: st for s, _, st, _ in store.source_health()}
    assert health["reddit"] == "ok"
    store.close()


def test_market_mode_cheap_then_top50(tmp_path):
    store = Store(tmp_path / "t.db"); store.init()
    reddit = FakeSource("reddit", [
        _post("1", "long $GME"), _post("2", "buy AMC"),
    ])
    xg = FakeSource("x_grok", [])
    report = run_cycle(
        {"reddit": reddit, "x_grok": xg}, store, _cfg(),
        frozenset({"GME", "AMC"}), "market", ["GME"], now=NOW,
    )
    # cheap phase called reddit with no tickers
    assert reddit.last_tickers == []
    # per-ticker phase: watchlist GME + top tickers from cheap source
    assert "GME" in xg.last_tickers
    assert "AMC" in xg.last_tickers
    assert report.inserted >= 2
    store.close()


def test_source_error_isolated(tmp_path):
    store = Store(tmp_path / "t.db"); store.init()
    good = FakeSource("reddit", [_post("1", "long $GME")])
    bad = FakeSource("x_grok", error=SourceError("boom"))
    report = run_cycle(
        {"reddit": good, "x_grok": bad}, store, _cfg(),
        frozenset({"GME"}), "watch", ["GME"], now=NOW,
    )
    assert report.inserted == 1
    assert "x_grok" in report.errors
    health = {s: st for s, _, st, _ in store.source_health()}
    assert health["x_grok"] == "error"
    assert health["reddit"] == "ok"
    store.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_watch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.watch'`.

- [ ] **Step 4: Write `src/contested/watch.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from .config import Config
from .models import TimeWindow, utcnow
from .normalizer import normalize_posts
from .sources.base import SourceError
from .store import Store

CHEAP_SOURCES = ("reddit", "stocktwits", "fourchan")
PER_TICKER_SOURCES = ("x_grok", "facebook", "instagram")


@dataclass
class CycleReport:
    inserted: int = 0
    per_source: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)


def _fetch_and_store(name, src, store, ticker_set, tickers, window, now, report) -> None:
    try:
        raws = src.fetch(tickers, window)
        events = normalize_posts(raws, ticker_set)
        n = store.upsert_events(events)
        report.inserted += n
        report.per_source[name] = report.per_source.get(name, 0) + n
        store.record_health(name, now, "ok", "")
    except SourceError as e:
        report.errors[name] = str(e)
        store.record_health(name, now, "error", str(e))
    except Exception as e:  # never let one source kill the cycle
        report.errors[name] = repr(e)
        store.record_health(name, now, "error", repr(e))


def run_cycle(sources, store: Store, cfg: Config, ticker_set, mode: str, watchlist, now=None) -> CycleReport:
    now = now or utcnow()
    wh = cfg.scores.window_hours()
    window = TimeWindow(start=now - timedelta(hours=wh), end=now)
    report = CycleReport()
    if mode == "market":
        for name in CHEAP_SOURCES:
            if name in sources:
                _fetch_and_store(name, sources[name], store, ticker_set, [], window, now, report)
        top = store.top_tickers_by_engagement(now, wh, 50)
        x_tickers = list(dict.fromkeys(list(watchlist) + top))
        for name in PER_TICKER_SOURCES:
            if name in sources:
                _fetch_and_store(name, sources[name], store, ticker_set, x_tickers, window, now, report)
    else:
        for name, src in sources.items():
            _fetch_and_store(name, src, store, ticker_set, list(watchlist), window, now, report)
    return report
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_watch.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/contested/watch.py tests/test_watch.py tests/conftest.py
git commit -m "feat: add collector run_cycle with market cost control and isolation"
```

---

### Task 13: Calibrate (anchor refit)

**Files:**
- Create: `src/contested/calibrate.py`
- Test: `tests/test_calibrate.py`

**Interfaces:**
- Consumes: `contested.store` (`Store`); `contested.scorer` (`score_ticker`); `contested.config` (`Config`, `ConfigError`); `contested.models` (`utcnow`).
- Produces: `calibrate(store, ticker_set, cfg, low_ticker, high_ticker, now=None) -> tuple[float, float]` (returns `(l_low, l_high)`; raises `ConfigError` if the high anchor's raw ≤ low anchor's raw).

- [ ] **Step 1: Write the failing test `tests/test_calibrate.py`**

```python
import math

from conftest import NOW
from contested.calibrate import calibrate
from contested.config import Config, ScoresCfg
from contested.models import Event
from contested.scorer import engagement_weight, score_ticker
from contested.store import Store


def _seed(store, ticker, n, upvotes):
    evs = [
        Event("t", f"{ticker}{i}", f"a{i}", "x", NOW, "bull" if i % 2 == 0 else "bear",
              1.0, engagement_weight(upvotes, 0, 0), (ticker,), "")
        for i in range(n)
    ]
    store.upsert_events(evs)


def test_calibrate_returns_log_anchors(tmp_path):
    store = Store(tmp_path / "t.db"); store.init()
    _seed(store, "MMM", 2, 9)      # low anchor, small raw
    _seed(store, "GME", 10, 1000)  # high anchor, large raw
    cfg = Config(scores=ScoresCfg(window="7d"))
    l_low, l_high = calibrate(store, frozenset({"MMM", "GME"}), cfg, "MMM", "GME", now=NOW)
    assert l_low < l_high
    # anchors equal the log10(1+raw) of each ticker's directional heat
    events = store.events_in_window(NOW, 168)
    def raw(t):
        s = score_ticker(events, t, NOW, 168, 48.0, 0.0, 1.0, 1.0)
        return s.bull_heat + s.bear_heat
    assert abs(l_low - math.log10(1 + raw("MMM"))) < 1e-9
    assert abs(l_high - math.log10(1 + raw("GME"))) < 1e-9
    store.close()


def test_calibrate_rejects_inverted(tmp_path):
    store = Store(tmp_path / "t.db"); store.init()
    _seed(store, "MMM", 2, 9)
    _seed(store, "GME", 2, 9)  # same raw -> inverted
    cfg = Config(scores=ScoresCfg(window="7d"))
    import pytest
    from contested.config import ConfigError
    with pytest.raises(ConfigError):
        calibrate(store, frozenset({"MMM", "GME"}), cfg, "MMM", "GME", now=NOW)
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calibrate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.calibrate'`.

- [ ] **Step 3: Write `src/contested/calibrate.py`**

```python
from __future__ import annotations

import math
from datetime import datetime

from .config import Config, ConfigError
from .models import utcnow
from .scorer import score_ticker
from .store import Store


def calibrate(store: Store, ticker_set, cfg: Config, low_ticker: str, high_ticker: str, now=None) -> tuple:
    now = now or utcnow()
    wh = cfg.scores.window_hours()
    events = store.events_in_window(now, wh)

    def raw(t):
        s = score_ticker(events, t, now, wh, cfg.scores.half_life_hours, 0.0, 1.0, cfg.scores.contested_floor)
        return s.bull_heat + s.bear_heat

    r_low = raw(low_ticker)
    r_high = raw(high_ticker)
    if r_high <= r_low:
        raise ConfigError(
            f"high anchor {high_ticker} raw ({r_high:.2f}) must exceed "
            f"low anchor {low_ticker} raw ({r_low:.2f})"
        )
    return math.log10(1.0 + r_low), math.log10(1.0 + r_high)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calibrate.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contested/calibrate.py tests/test_calibrate.py
git commit -m "feat: add calibrate to refit score anchors from tickers"
```

---

### Task 14: CLI (scan, ticker, sources, calibrate, update-tickers, watch)

**Files:**
- Create: `src/contested/cli.py`
- Create: `src/contested/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above (`config`, `store`, `scorer`, `normalizer`, `tickerlist`, `calibrate`, `watch`, `sources.build_sources`, `models`).
- Produces: `app` (typer `Typer`) with commands `scan`, `watch`, `ticker`, `calibrate`, `sources`, `update-tickers`; helpers `sparkline(values) -> str`, `format_scan_lines(scores) -> list[str]`, `health_line(cfg, store) -> str`. The package is already installed editable, so `contested` console script and `python -m contested` both call `app`.

- [ ] **Step 1: Write the failing test `tests/test_cli.py`**

```python
from datetime import timedelta

import pytest
from typer.testing import CliRunner

from conftest import NOW
from contested.cli import app
from contested.models import Event, Score
from contested.scorer import engagement_weight
from contested.store import Store

runner = CliRunner()


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "tickers_us.txt").write_text("GME\nAMC\nMMM\n", encoding="utf-8")
    store = Store(tmp_path / "data" / "contested.db")
    store.init()
    evs = [
        Event("t", "1", "a", "long $GME", NOW, "bull", 3.0, engagement_weight(1000, 0, 0), ("GME",), ""),
        Event("t", "2", "b", "sell $GME", NOW, "bear", 3.0, engagement_weight(1000, 0, 0), ("GME",), ""),
        Event("t", "3", "c", "long $AMC", NOW, "bull", 1.0, engagement_weight(9, 0, 0), ("AMC",), ""),
        Event("t", "4", "d", "sell $AMC", NOW, "bear", 1.0, engagement_weight(9, 0, 0), ("AMC",), ""),
    ]
    store.upsert_events(evs)
    store.save_score(Score("GME", NOW, 168, 90, 80, 10.0, 9.0, 2, 2))
    store.save_score(Score("AMC", NOW, 168, 20, 10, 1.0, 0.9, 1, 1))
    return tmp_path


def test_scan_prints_ranked(seeded):
    r = runner.invoke(app, ["scan", "--window", "7d", "--top", "10"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    out = r.output
    assert "GME" in out and "AMC" in out
    # GME ranks above AMC by momentum
    assert out.index("GME") < out.index("AMC")
    assert "sources:" in out


def test_scan_json(seeded):
    import json
    r = runner.invoke(app, ["scan", "--json"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["mode"] == "watch"
    assert data["scores"][0]["ticker"] == "GME"


def test_scan_requires_ticker_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["scan"], catch_exceptions=False)
    assert r.exit_code != 0
    assert "update-tickers" in r.output


def test_ticker_deep_dive(seeded):
    r = runner.invoke(app, ["ticker", "GME"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert "GME" in r.output
    assert "bull" in r.output.lower()


def test_sources_command(seeded):
    r = runner.invoke(app, ["sources"], catch_exceptions=False)
    assert r.exit_code == 0
    assert "reddit" in r.output


def test_sparkline_monotonic():
    from contested.cli import sparkline
    assert len(sparkline([1, 2, 3, 4])) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'contested.cli'`.

- [ ] **Step 3: Write `src/contested/cli.py`**

```python
from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path

import typer

from . import __version__
from .calibrate import calibrate as run_calibrate
from .config import (
    Config,
    ConfigError,
    load_config,
    load_watchlist,
    parse_duration,
    parse_window,
    resolve_config_path,
)
from .models import Score, utcnow
from .scorer import score_all
from .store import Store
from .tickerlist import TickerListError, download_ticker_list
from .watch import run_cycle
from .sources import build_sources

TICKER_FILE = Path("data") / "tickers_us.txt"
_SPARK = "▁▂▃▄▅▆▇█"


app = typer.Typer(help="Contested sentiment scanner for US-listed stocks.")


def sparkline(values: list) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return _SPARK[1] * len(values)
    step = (len(_SPARK) - 1) / (hi - lo)
    return "".join(_SPARK[int((v - lo) * step)] for v in values)


def _ticker_set_or_exit():
    if not TICKER_FILE.is_file():
        typer.echo("error: no ticker list. Run: contested update-tickers")
        raise typer.Exit(code=2)
    from .tickerlist import load_ticker_set
    return load_ticker_set(TICKER_FILE)


def _store(cfg: Config) -> Store:
    store = Store(cfg.db_path)
    store.init()
    return store


def health_line(cfg: Config, store: Store) -> str:
    health = {s: (st, note) for s, _, st, note in store.source_health()}
    parts = []
    for name in cfg.sources:
        if name in health:
            mark = "✓" if health[name][0] == "ok" else "✗"
            parts.append(f"{name}{mark}")
        else:
            parts.append(f"{name}–")
    return "sources: " + " ".join(parts)


def _resolve(cfg: Config, window: str | None) -> int:
    return parse_window(window or cfg.scores.window)


@app.command()
def scan(
    window: str = typer.Option(None, help="e.g. 7d, 24h (default from config)"),
    top: int = typer.Option(25, help="number of tickers to show"),
    market: bool = typer.Option(False, help="market-wide discovery mode"),
    watchlist: str = typer.Option(None, help="path to watchlist file"),
    fetch: bool = typer.Option(False, help="run one collector cycle first"),
    source: list = typer.Option(None, help="filter to specific sources"),
    as_json: bool = typer.Option(False, "--json", help="emit JSON"),
    config: str = typer.Option(None, help="path to contested.toml"),
) -> None:
    cfg = load_config(config)
    store = _store(cfg)
    now = utcnow()
    ticker_set = _ticker_set_or_exit()
    wl_path = watchlist or cfg.watchlist_path
    watch = load_watchlist(wl_path)
    if fetch:
        sources = {k: v for k, v in build_sources(cfg).items() if not source or k in source}
        run_cycle(sources, store, cfg, ticker_set, "market" if market else "watch", watch, now=now)
    wh = _resolve(cfg, window)
    events = store.events_in_window(now, wh)
    mode = "market" if market else "watch"
    if mode == "watch":
        tickers = [t for t in watch if t in ticker_set] or list(ticker_set)
    else:
        tickers = store.tickers_in_window(now, wh)
    scores = score_all(
        events, tickers, now, wh, cfg.scores.half_life_hours,
        cfg.scores.l_low, cfg.scores.l_high, cfg.scores.contested_floor,
    )
    scores.sort(key=lambda s: (s.momentum, s.contested), reverse=True)
    scores = scores[:top]
    if as_json:
        payload = {
            "ts": now.isoformat(),
            "window_hours": wh,
            "mode": mode,
            "sources": {s: st for s, _, st, _ in store.source_health()},
            "scores": [
                {
                    "ticker": s.ticker, "momentum": s.momentum, "contested": s.contested,
                    "bull_heat": s.bull_heat, "bear_heat": s.bear_heat,
                    "n_bull": s.n_bull, "n_bear": s.n_bear,
                }
                for s in scores
            ],
        }
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(f"# contested scan  window={wh}h  mode={mode}  top={top}")
    typer.echo(health_line(cfg, store))
    typer.echo(f"{'#':>3}  {'TICKER':<7} {'MOMENTUM':>8} {'CONTESTED':>9}  {'BULL':>9} {'BEAR':>9}")
    for i, s in enumerate(scores, 1):
        typer.echo(f"{i:>3}  {s.ticker:<7} {s.momentum:>8} {s.contested:>9}  {s.bull_heat:>9.1f} {s.bear_heat:>9.1f}")
    store.close()


@app.command()
def ticker(
    symbol: str,
    window: str = typer.Option(None),
    top_posts: int = typer.Option(5),
    as_json: bool = typer.Option(False, "--json"),
    config: str = typer.Option(None),
) -> None:
    cfg = load_config(config)
    store = _store(cfg)
    now = utcnow()
    wh = _resolve(cfg, window)
    events = [e for e in store.events_in_window(now, wh) if symbol.upper() in e.tickers]
    s = score_all(events, [symbol.upper()], now, wh, cfg.scores.half_life_hours,
                  cfg.scores.l_low, cfg.scores.l_high, cfg.scores.contested_floor)[0]
    hist = store.score_history(symbol.upper(), wh)
    spark = sparkline([h.momentum for h in hist])
    if as_json:
        typer.echo(json.dumps({
            "ticker": symbol.upper(), "momentum": s.momentum, "contested": s.contested,
            "bull_heat": s.bull_heat, "bear_heat": s.bear_heat,
            "n_bull": s.n_bull, "n_bear": s.n_bear, "sparkline": spark,
        }, indent=2))
        return
    typer.echo(f"=== {symbol.upper()}  window={wh}h ===")
    typer.echo(f"momentum={s.momentum}  contested={s.contested}")
    typer.echo(f"bull heat={s.bull_heat:.1f} (n={s.n_bull})   bear heat={s.bear_heat:.1f} (n={s.n_bear})")
    typer.echo(f"history: {spark}")

    def _top(side):
        picks = [e for e in events
                 if (side == "bull" and e.sentiment in ("bull", "mixed"))
                 or (side == "bear" and e.sentiment in ("bear", "mixed"))]
        picks.sort(key=lambda e: e.intensity * e.engagement, reverse=True)
        for e in picks[:top_posts]:
            typer.echo(f"  [{side}] ({e.source}) {e.text[:100]}")

    typer.echo("top bull posts:")
    _top("bull")
    typer.echo("top bear posts:")
    _top("bear")
    store.close()


@app.command()
def sources(config: str = typer.Option(None)) -> None:
    cfg = load_config(config)
    store = _store(cfg)
    health = {s: (st, note) for s, _, st, note in store.source_health()}
    for name, scfg in cfg.sources.items():
        state = "enabled" if scfg.enabled else "disabled"
        last = health.get(name)
        last_s = f"  last={last[0]} {last[1]}" if last else "  last=never"
        typer.echo(f"{name:<10} {state:<8}{last_s}")
    store.close()


@app.command()
def calibrate(
    low: str = typer.Option(..., "--low"),
    high: str = typer.Option(..., "--high"),
    config: str = typer.Option(None),
) -> None:
    import tomli_w
    cfg = load_config(config)
    store = _store(cfg)
    from .tickerlist import load_ticker_set
    ticker_set = _ticker_set_or_exit()
    l_low, l_high = run_calibrate(store, ticker_set, cfg, low.upper(), high.upper())
    path = resolve_config_path(config)
    data = {}
    if path.is_file():
        import tomllib
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    data.setdefault("scores", {})["l_low"] = round(l_low, 4)
    data["scores"]["l_high"] = round(l_high, 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        tomli_w.dump(data, fh)
    typer.echo(f"calibrated: l_low={l_low:.4f} l_high={l_high:.4f} (written to {path})")
    store.close()


@app.command("update-tickers")
def update_tickers() -> None:
    try:
        got = download_ticker_list(TICKER_FILE)
    except TickerListError as e:
        typer.echo(f"error: {e}")
        raise typer.Exit(code=1)
    typer.echo(f"updated ticker list: {len(got)} US tickers -> {TICKER_FILE}")


@app.command()
def watch(
    every: str = typer.Option("15m", help="interval, e.g. 15m, 1h"),
    once: bool = typer.Option(False, help="run a single cycle and exit"),
    market: bool = typer.Option(False),
    config: str = typer.Option(None),
) -> None:
    cfg = load_config(config)
    store = _store(cfg)
    ticker_set = _ticker_set_or_exit()
    sources = build_sources(cfg)
    watchlist = load_watchlist(cfg.watchlist_path)
    mode = "market" if market else "watch"
    interval = parse_duration(every)
    while True:
        report = run_cycle(sources, store, cfg, ticker_set, mode, watchlist)
        typer.echo(health_line(cfg, store) + f"  inserted={report.inserted}")
        for name, err in report.errors.items():
            typer.echo(f"  ! {name}: {err}")
        if once:
            break
        time.sleep(interval)
    store.close()
```

- [ ] **Step 4: Create `src/contested/__main__.py`**

```python
from .cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: all PASS.

- [ ] **Step 6: Verify the console entry and module entry both work**

Run: `python -m contested --help`
Expected: prints the command list (`scan`, `watch`, `ticker`, `calibrate`, `sources`, `update-tickers`).

- [ ] **Step 7: Commit**

```bash
git add src/contested/cli.py src/contested/__main__.py tests/test_cli.py
git commit -m "feat: add typer CLI with scan, ticker, sources, calibrate, update-tickers, watch"
```

---

### Task 15: README, live smoke script, end-to-end test, packaging check

**Files:**
- Create: `README.md`
- Create: `scripts/smoke_live.py`
- Test: `tests/test_e2e.py`
- Modify: `.gitignore` (ensure `scripts/` not ignored — it should be tracked)

**Interfaces:**
- Consumes: the full package.
- Produces: runnable `contested` CLI documented; a manual live smoke script; an end-to-end test proving `watch --once` (fake sources) → `scan` produces a ranked list; a clean `pip install -e .` + full test-suite run.

- [ ] **Step 1: Create `scripts/smoke_live.py` (manual, not run in CI)**

```python
"""Manual live smoke test: fetch one page from each enabled source.

Run:  python scripts/smoke_live.py
Requires network and, for x_grok, GROK_BASE_URL + GROK_API_KEY.
"""
import sys
from datetime import timedelta

from contested.config import load_config
from contested.models import TimeWindow, utcnow
from contested.sources import build_sources
from contested.sources.base import SourceError


def main() -> int:
    cfg = load_config()
    sources = build_sources(cfg)
    now = utcnow()
    window = TimeWindow(start=now - timedelta(hours=24), end=now)
    failures = 0
    for name, src in sorted(sources.items()):
        try:
            posts = src.fetch([], window)
            print(f"OK   {name:<10} {len(posts)} posts")
        except SourceError as e:
            failures += 1
            print(f"FAIL {name:<10} {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERR  {name:<10} {e!r}")
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write the end-to-end test `tests/test_e2e.py`**

```python
import json

from typer.testing import CliRunner

from conftest import FakeSource, NOW
from contested.cli import app
from contested.models import RawPost

runner = CliRunner()


def test_watch_once_then_scan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "tickers_us.txt").write_text("GME\nAMC\n", encoding="utf-8")
    (tmp_path / "data" / "watchlist.txt").write_text("GME\n", encoding="utf-8")

    # Patch build_sources to return in-process fakes (no network).
    import contested.cli as cli
    fakes = {
        "reddit": FakeSource("reddit", [
            RawPost("reddit", "1", "a", "long $GME to the moon", NOW, upvotes=1000),
        ]),
        "x_grok": FakeSource("x_grok", [
            RawPost("x_grok", "2", "b", "sell $GME", NOW, upvotes=1000),
        ]),
    }
    monkeypatch.setattr(cli, "build_sources", lambda cfg: fakes)

    r1 = runner.invoke(app, ["watch", "--once"], catch_exceptions=False)
    assert r1.exit_code == 0, r1.output
    assert "inserted=2" in r1.output

    r2 = runner.invoke(app, ["scan", "--json"], catch_exceptions=False)
    assert r2.exit_code == 0, r2.output
    data = json.loads(r2.output)
    tickers = [s["ticker"] for s in data["scores"]]
    assert "GME" in tickers
```

- [ ] **Step 3: Create `README.md`**

```markdown
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
```

- [ ] **Step 4: Run the end-to-end test**

Run: `python -m pytest tests/test_e2e.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest -q`
Expected: all PASS (all test files green).

- [ ] **Step 6: Verify packaging and entry points from a clean reinstall**

Run:
```bash
python -m pip install -e . --force-reinstall --no-deps
python -m contested --help
contested --help 2>/dev/null || python -m contested --help
```
Expected: the command list prints; no import errors.

- [ ] **Step 7: Commit**

```bash
git add README.md scripts/smoke_live.py tests/test_e2e.py
git commit -m "docs: add README, live smoke script, and end-to-end test"
```

- [ ] **Step 8: Run the entire suite one final time and show the summary**

Run: `python -m pytest -q`
Expected: green summary line (e.g. `NN passed`).

---

## Self-Review

**1. Spec coverage** — mapping each spec requirement to a task:
- Purpose (two 0–100 metrics, anchors) → Task 3 (scorer + anchor tests), Task 13 (calibrate).
- Sources (reddit, x_grok, stocktwits, fourchan; fb/ig stubs) → Tasks 8, 10, 9, 11.
- Watchlist + market-wide discovery modes → Task 12 (run_cycle), Task 14 (scan --market).
- On-demand `scan` + scheduled `watch` sharing one SQLite store → Tasks 4, 12, 14.
- Architecture (four layers) → Tasks 7–14.
- Scoring math (engagement, decay, intensity, mixed 0.6, band, contested floor) → Task 3.
- Cost control (cheap market-wide, X for watchlist ∪ top-50) → Task 12.
- CLI commands + health line + `--json` → Task 14.
- Config (contested.toml, env secrets, validation, fail-fast) → Task 1, Task 11.
- Error handling (per-source isolation, retry/backoff, fail-fast config) → Tasks 7, 12, 11.
- Testing (scorer fixtures gme/3m/one-sided/mixed/decay/dedupe, per-source, no network) → Tasks 3, 4, 8–12, 15.
- Project layout (exact files) → File Structure + each task.

Gaps found and addressed: ticker-list download source (NASDAQ `nasdaqlisted.txt` + `otherlisted.txt`) specified in Task 6; console entry point + `__main__` in Task 14; editable install + git identity in Task 1.

**2. Placeholder scan** — no TBD/TODO; every code step has full code; tests reference only types/functions defined in an earlier task. (The `__import__` usage in test_calibrate/test_e2e is deliberate to avoid import-order issues, not a placeholder.)

**3. Type consistency** — verified across tasks:
- `Event` fields (`source, post_id, author, text, ts, sentiment, intensity, engagement, tickers, url`) consistent in models (T1), normalizer (T5), store (T4), scorer (T3), watch (T12), cli (T14).
- `RawPost` fields consistent across models (T1) and all sources (T8–T11).
- `Score` fields consistent in models (T1), scorer (T3), store (T4), cli (T14).
- `Store` method signatures (T4) match usage in watch (T12), calibrate (T13), cli (T14).
- `build_sources(cfg) -> dict` (T11) matches usage in cli (T14) and test_e2e monkeypatch.
- `run_cycle(sources, store, cfg, ticker_set, mode, watchlist, now)` (T12) matches cli (T14) and test_watch (T12).
- `calibrate(store, ticker_set, cfg, low, high, now)` (T13) matches cli (T14).
- `config` dataclasses (`Config`, `ScoresCfg`, `SourceCfg`, `load_config`, `load_watchlist`, `resolve_config_path`, `parse_window`) (T1) match all consumers.

Naming note (bug caught in self-review and fixed): the CLI command `calibrate` and the module function `calibrate` would collide — inside `cli.py` the `def calibrate(...)` decorated with `@app.command()` rebinds the module-global name, so a bare `calibrate(...)` call in the body would resolve to the typer-wrapped command (empirically a `TypeError`). The import is therefore aliased `from .calibrate import calibrate as run_calibrate` and the body calls `run_calibrate(...)`. Verified: `typer.Exit(code=2)` under `CliRunner(catch_exceptions=False)` yields `exit_code=2` (so `test_scan_requires_ticker_list` passes) and does not need a `try/except SystemExit`.

Final consistency pass (two more fixes): the two `health` lines in `tests/test_watch.py` used `dict(s for s, _, st, _ in rows)`, which feeds bare strings to `dict()` (each string must unpack to a 2-item pair → `ValueError` at runtime); both now use the `{s: st for s, _, st, _ in ...}` comprehension that `cli.health_line` already uses correctly. And `tests/conftest.py` pins `NOW` to the live `utcnow()` truncated to seconds instead of a fixed date: `test_watch`/`test_calibrate` pass `now=NOW` explicitly so they were date-independent, but `test_cli`/`test_e2e` scan with the real clock, so a pinned NOW would make them silently fail once that instant aged out of the 168h window. With a live NOW, seeded events are seconds old, so decay weight ≈ 1 and the asserted rankings (GME 14 > AMC 2; GME present in e2e scores) hold at any future run time.
