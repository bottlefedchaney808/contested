from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..models import RawPost, TimeWindow
from .base import http_get_json

_UA_DEFAULT = "contested/0.1 (local sentiment scanner)"


class RedditSource:
    name = "reddit"

    def __init__(self, client=None, client_id="", client_secret="",
                 subs=("wallstreetbets", "stocks", "investing", "Options"),
                 user_agent=_UA_DEFAULT):
        self._client = client or httpx.Client(timeout=20.0)
        self._own_client = client is None
        self._client_id = client_id
        self._client_secret = client_secret
        self._subs = tuple(subs)
        self._ua = user_agent
        self._token = None

    def _headers(self):
        h = {"User-Agent": self._ua, "Accept": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _maybe_token(self):
        if self._token is not None or not (self._client_id and self._client_secret):
            return
        try:
            resp = self._client.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(self._client_id, self._client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": self._ua},
            )
            if resp.status_code == 200:
                self._token = resp.json().get("access_token")
        except Exception:
            self._token = None

    def _children(self, url):
        data = http_get_json(url, self._client, headers=self._headers())
        return data.get("data", {}).get("children", [])

    def _to_post(self, c, source_id_prefix=""):
        d = c.get("data", {})
        created = d.get("created_utc")
        if created is None:
            return None
        ts = datetime.fromtimestamp(created, tz=timezone.utc)
        text = (d.get("title", "") + " " + d.get("selftext", "")).strip()
        if not text:
            return None
        return RawPost(
            source=self.name,
            post_id=source_id_prefix + str(d.get("id")),
            author=str(d.get("author", "")),
            text=text,
            ts=ts,
            upvotes=int(d.get("score", 0) or 0),
            comments=int(d.get("num_comments", 0) or 0),
            reposts=0,
            url="https://www.reddit.com" + d.get("permalink", ""),
        )

    def _in_window(self, post, window):
        return window.start <= post.ts <= window.end

    def fetch(self, tickers, window: TimeWindow):
        self._maybe_token()
        posts = []
        if tickers:
            for t in tickers:
                url = f"https://www.reddit.com/search.json?q=%24{t}&sort=new&limit=100"
                for c in self._children(url):
                    p = self._to_post(c)
                    if p and self._in_window(p, window):
                        posts.append(p)
        else:
            for sub in self._subs:
                url = f"https://www.reddit.com/r/{sub}/new.json?limit=100"
                for c in self._children(url):
                    p = self._to_post(c)
                    if p and self._in_window(p, window):
                        posts.append(p)
        return posts
