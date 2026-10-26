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
