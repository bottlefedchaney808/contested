from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import RawPost, TimeWindow
from .base import http_get_json


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class StocktwitsSource:
    name = "stocktwits"

    def __init__(self, client=None):
        self._client = client or httpx.Client(timeout=20.0)

    def _messages(self, url):
        data = http_get_json(url, self._client)
        return data.get("messages", [])

    def _to_post(self, m):
        created = m.get("created_at")
        if not created:
            return None
        try:
            ts = _parse_ts(created)
        except ValueError:
            return None
        body = m.get("body", "")
        if not body:
            return None
        react = m.get("reactions", {}) or {}
        return RawPost(
            source=self.name,
            post_id=str(m.get("id")),
            author=str((m.get("user") or {}).get("username", "")),
            text=body,
            ts=ts,
            upvotes=int(react.get("like", 0) or 0),
            comments=int(m.get("replies", 0) or 0),
            reposts=int(m.get("retweets", 0) or 0),
            url="https://stocktwits.com/message/" + str(m.get("id", "")),
        )

    def _in_window(self, post, window):
        return window.start <= post.ts <= window.end

    def fetch(self, tickers, window: TimeWindow):
        posts = []
        if tickers:
            for t in tickers:
                url = f"https://api.stocktwits.com/api/2/streams/symbol/{t}.json?limit=200"
                for m in self._messages(url):
                    p = self._to_post(m)
                    if p and self._in_window(p, window):
                        posts.append(p)
        else:
            # The global message stream now 404s. Trending symbols still works;
            # pull each symbol's stream, which is the same shape as per-ticker mode.
            data = http_get_json(
                "https://api.stocktwits.com/api/2/trending/symbols.json", self._client)
            symbols = [s.get("symbol") for s in data.get("symbols", []) if s.get("symbol")]
            for t in symbols:
                url = f"https://api.stocktwits.com/api/2/streams/symbol/{t}.json?limit=200"
                for m in self._messages(url):
                    p = self._to_post(m)
                    if p and self._in_window(p, window):
                        posts.append(p)
        return posts
