from __future__ import annotations

import re
from pathlib import Path

import httpx

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_TOK = re.compile(r"^[A-Z][A-Z.]{1,9}$")


class TickerListError(Exception):
    pass


def load_ticker_set(path: str | Path) -> frozenset:
    p = Path(path)
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip().upper()
        if t and not t.startswith("#") and _TOK.match(t):
            out.add(t)
    return frozenset(out)


def _parse_first_column(text: str) -> set:
    out = set()
    for line in text.splitlines():
        first = re.split(r"[|\t]", line, maxsplit=1)[0].strip().upper()
        if first and first != "SYMBOL" and _TOK.match(first):
            out.add(first)
    return out


def download_ticker_list(dest: str | Path, client: httpx.Client | None = None) -> frozenset:
    own = client is None
    if own:
        client = httpx.Client(timeout=30.0)
    try:
        union = set()
        for url in (NASDAQ_LISTED_URL, OTHER_LISTED_URL):
            resp = client.get(url)
            if resp.status_code != 200:
                raise TickerListError(f"HTTP {resp.status_code} fetching {url}")
            union |= _parse_first_column(resp.text)
        if not union:
            raise TickerListError("ticker list empty after parse")
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_text("\n".join(sorted(union)) + "\n", encoding="utf-8")
        return frozenset(union)
    finally:
        if own:
            client.close()
