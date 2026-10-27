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
        url = str(r.url)
        if "/trending/symbols.json" in url:
            return httpx.Response(200, json={"symbols": [{"symbol": "GME"}]})
        assert "/streams/symbol/GME.json" in url
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
