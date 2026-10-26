from __future__ import annotations

import re
from typing import Sequence

from .models import Event, RawPost
from .scorer import engagement_weight
from .sentiment import classify, text_intensity

_CASE_RE = re.compile(r"\$([A-Za-z]{1,5})\b")
_WORD_RE = re.compile(r"\b[A-Za-z]{3,5}\b")


def extract_tickers(text: str, ticker_set: frozenset) -> tuple:
    found = []
    seen = set()
    for m in _CASE_RE.finditer(text):
        t = m.group(1).upper()
        if t in ticker_set and t not in seen:
            seen.add(t)
            found.append(t)
    for m in _WORD_RE.finditer(text):
        t = m.group(0).upper()
        if t in ticker_set and t not in seen:
            seen.add(t)
            found.append(t)
    return tuple(found)


def normalize_posts(raws: Sequence[RawPost], ticker_set: frozenset) -> list:
    out = []
    for r in raws:
        tickers = extract_tickers(r.text, ticker_set)
        if not tickers:
            continue
        out.append(
            Event(
                source=r.source,
                post_id=r.post_id,
                author=r.author,
                text=r.text,
                ts=r.ts,
                sentiment=classify(r.text),
                intensity=text_intensity(r.text),
                engagement=engagement_weight(r.upvotes, r.comments, r.reposts),
                tickers=tickers,
                url=r.url,
            )
        )
    return out
