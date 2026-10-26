from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import RawPost, TimeWindow
from .base import SourceError, http_post_json


def _parse_ts(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class XGrokSource:
    name = "x_grok"

    def __init__(self, client=None, base_url="", api_key=""):
        self._client = client or httpx.Client(timeout=30.0)
        self._base_url = (base_url or "https://api.x.ai").rstrip("/")
        self._api_key = api_key

    def _headers(self):
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _search(self, ticker, window):
        payload = {
            "query": f"${ticker}",
            "from_date": window.start.date().isoformat(),
            "to_date": window.end.date().isoformat(),
        }
        data = http_post_json(f"{self._base_url}/v1/x_search", self._client,
                              payload=payload, headers=self._headers())
        rows = data.get("results") or data.get("data") or []
        posts = []
        for i, row in enumerate(rows):
            post = row.get("post", row)
            contents = post.get("contents", {}) or {}
            text = contents.get("text") or post.get("text") or row.get("text") or ""
            if not text:
                continue
            ts = _parse_ts(post.get("created_at") or row.get("created_at"))
            if ts is None:
                continue
            if not (window.start <= ts <= window.end):
                continue
            user = (post.get("user") or {})
            posts.append(RawPost(
                source=self.name,
                post_id=str(post.get("id") or post.get("rest_id") or f"row{i}"),
                author=str(user.get("username", "") if isinstance(user, dict) else user),
                text=text,
                ts=ts,
                upvotes=int(post.get("like_count") or post.get("likes") or 0),
                comments=int(post.get("reply_count") or 0),
                reposts=int(post.get("retweet_count") or 0),
                url=str(post.get("url") or ""),
            ))
        return posts

    def fetch(self, tickers, window: TimeWindow):
        posts = []
        for t in tickers:
            posts.extend(self._search(t, window))
        return posts
