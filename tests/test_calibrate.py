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
