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
