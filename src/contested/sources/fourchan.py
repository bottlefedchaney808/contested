from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import RawPost, TimeWindow
from .base import http_get_json


class FourChanSource:
    name = "fourchan"

    def __init__(self, client=None, board="biz"):
        self._client = client or httpx.Client(timeout=20.0)
        self._board = board

    def fetch(self, tickers, window: TimeWindow):
        url = f"https://a.4cdn.org/{self._board}/catalog.json"
        threads = http_get_json(url, self._client)
        posts = []
        for t in threads:
            last = t.get("last_time")
            if last is None:
                continue
            ts = datetime.fromtimestamp(last, tz=timezone.utc)
            if not (window.start <= ts <= window.end):
                continue
            text = ((t.get("sub", "") or "") + " " + (t.get("com", "") or "")).strip()
            if not text:
                continue
            posts.append(RawPost(
                source=self.name,
                post_id=str(t.get("No")),
                author="4anon",
                text=text,
                ts=ts,
                upvotes=int(t.get("cap", 0) or 0),
                comments=int(t.get("replies", 0) or 0),
                reposts=0,
                url=f"https://boards.4chan.org/{self._board}/thread/{t.get('No')}",
            ))
        return posts
