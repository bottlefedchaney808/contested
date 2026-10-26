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
