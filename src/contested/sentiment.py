from __future__ import annotations

import re

BULL_TERMS: frozenset = frozenset({
    "long", "moon", "to the moon", "rip it", "buy the dip",
    "accumulate", "accumulation", "buying", "buy", "breakout",
    "upside", "rally", "bullish", "undervalued", "underrated",
    "yolo", "all in", "all-in", "diamond hands", "hodl", "pump", "green",
})

BEAR_TERMS: frozenset = frozenset({
    "short", "selling", "sell", "overvalued", "overrated", "bearish",
    "dump", "bankruptcy", "bankrupt", "delist", "fraud", "ripoff",
    "rip off", "exit", "downtrend", "downside", "red flag", "scam",
    "paper hands", "bagholder", "crash", "red",
})

_STRONG_MODALS = ("obviously", "no doubt", "everyone knows", "100%", "certain", "for sure")
_CONVICTION = (
    "all in", "all-in", "i'm in", "i am in", "bought",
    "sold everything", "selling everything", "yolo",
)


def _hit(term: str, text_lower: str) -> bool:
    if " " in term:
        return term in text_lower
    return re.search(r"\b" + re.escape(term) + r"\b", text_lower) is not None


def _count_hits(terms: frozenset, text_lower: str) -> int:
    return sum(1 for t in terms if _hit(t, text_lower))


def classify(text: str) -> str:
    tl = text.lower()
    bull = _count_hits(BULL_TERMS, tl)
    bear = _count_hits(BEAR_TERMS, tl)
    if bull > 0 and bear > 0:
        return "mixed"
    if bull > 0:
        return "bull"
    if bear > 0:
        return "bear"
    return "neutral"


def text_intensity(text: str) -> float:
    i = 1.0
    letters = [c for c in text if c.isalpha()]
    caps = (sum(1 for c in letters if c.isupper()) / len(letters)) if letters else 0.0
    tl = text.lower()
    if caps > 0.3 or text.count("!") >= 2 or any(m in tl for m in _STRONG_MODALS):
        i += 1.0
    if any(c in tl for c in _CONVICTION):
        i += 1.0
    return min(3.0, i)
