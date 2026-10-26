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
