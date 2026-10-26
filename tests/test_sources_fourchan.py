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
