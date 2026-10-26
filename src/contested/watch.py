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
