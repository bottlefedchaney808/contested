from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Sequence

from .models import BEAR, BULL, Event, MIXED, Score

MIXED_WEIGHT = 0.6
MAX_INTENSITY = 4.0
REPETITION_THRESHOLD = 3


def engagement_weight(upvotes: int, comments: int, reposts: int) -> float:
    return math.log10(1.0 + upvotes + 4.0 * comments + 2.0 * reposts)


def decay_weight(age_hours: float, half_life_hours: float) -> float:
    if age_hours <= 0:
        return 1.0
    return math.exp(-math.log(2.0) * age_hours / half_life_hours)


def band(raw: float, l_low: float, l_high: float) -> int:
    if raw < 0:
        raw = 0.0
    if l_high <= l_low:
        return 10
    l = math.log10(1.0 + raw)
    score = 10.0 + 90.0 * (l - l_low) / (l_high - l_low)
    return max(0, min(100, int(round(score))))


def _stances(sentiment: str) -> tuple:
    if sentiment == BULL:
        return (BULL,)
    if sentiment == BEAR:
        return (BEAR,)
    if sentiment == MIXED:
        return (BULL, BEAR)
    return ()


def score_ticker(events, ticker, now, window_hours, half_life_hours, l_low, l_high, contested_floor) -> Score:
    rel = [
        e
        for e in events
        if ticker in e.tickers
        and (now - e.ts).total_seconds() / 3600.0 <= window_hours
    ]
    stance_counts: Counter = Counter()
    for e in rel:
        for s in _stances(e.sentiment):
            stance_counts[(e.author, s)] += 1
    bull_heat = 0.0
    bear_heat = 0.0
    n_bull = 0
    n_bear = 0
    for e in rel:
        stances = _stances(e.sentiment)
        if not stances:
            continue
        age_h = (now - e.ts).total_seconds() / 3600.0
        w = decay_weight(age_h, half_life_hours)
        weight = MIXED_WEIGHT if e.sentiment == MIXED else 1.0
        for s in stances:
            rep = 1.0 if stance_counts[(e.author, s)] >= REPETITION_THRESHOLD else 0.0
            eff = min(MAX_INTENSITY, e.intensity + rep)
            bull_bear = s == BULL
            contrib = eff * e.engagement * weight * w
            if bull_bear:
                bull_heat += contrib
                n_bull += 1
            else:
                bear_heat += contrib
                n_bear += 1
    r_m = bull_heat + bear_heat
    momentum = band(r_m, l_low, l_high)
    if bull_heat < contested_floor or bear_heat < contested_floor:
        contested = 0
    else:
        balance = 2.0 * min(bull_heat, bear_heat) / r_m if r_m > 0 else 0.0
        contested = band(balance * r_m, l_low, l_high)
    return Score(
        ticker=ticker,
        ts=now,
        window_hours=window_hours,
        momentum=momentum,
        contested=contested,
        bull_heat=bull_heat,
        bear_heat=bear_heat,
        n_bull=n_bull,
        n_bear=n_bear,
    )


def score_all(events, tickers, now, window_hours, half_life_hours, l_low, l_high, contested_floor) -> list:
    return [
        score_ticker(events, t, now, window_hours, half_life_hours, l_low, l_high, contested_floor)
        for t in tickers
    ]
