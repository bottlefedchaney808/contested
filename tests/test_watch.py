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
