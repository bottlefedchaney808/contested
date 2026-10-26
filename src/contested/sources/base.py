from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

import httpx

from ..models import RawPost, TimeWindow


class SourceError(Exception):
    pass


@runtime_checkable
class Source(Protocol):
    name: str

    def fetch(self, tickers: list, window: TimeWindow) -> list:
        ...


def _request(client: httpx.Client, method: str, url: str, retries: int, backoff: float, **kwargs) -> dict:
    last = None
    for attempt in range(retries + 1):
        resp = client.request(method, url, **kwargs)
        if resp.status_code == 200:
            return resp.json()
        last = f"HTTP {resp.status_code}"
        if 400 <= resp.status_code < 500 and resp.status_code != 429:
            break  # client error: don't retry
        if attempt < retries:
            time.sleep(backoff)
    raise SourceError(f"{method} {url} failed: {last}")


def http_get_json(url, client, params=None, headers=None, retries=2, backoff=0.0) -> dict:
    return _request(client, "GET", url, retries, backoff, params=params, headers=headers)


def http_post_json(url, client, payload=None, headers=None, retries=2, backoff=0.0) -> dict:
    return _request(client, "POST", url, retries, backoff, json=payload, headers=headers)
