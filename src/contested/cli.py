from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path

import httpx
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
    source: list[str] = typer.Option(None, help="filter to specific sources"),
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
    except (TickerListError, httpx.HTTPError) as e:
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
