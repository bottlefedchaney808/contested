from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

BULL = "bull"
BEAR = "bear"
NEUTRAL = "neutral"
MIXED = "mixed"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


@dataclass(frozen=True)
class RawPost:
    source: str
    post_id: str
    author: str
    text: str
    ts: datetime
    upvotes: int = 0
    comments: int = 0
    reposts: int = 0
    url: str = ""


@dataclass(frozen=True)
class Event:
    source: str
    post_id: str
    author: str
    text: str
    ts: datetime
    sentiment: str
    intensity: float
    engagement: float
    tickers: tuple
    url: str = ""


@dataclass(frozen=True)
class Score:
    ticker: str
    ts: datetime
    window_hours: int
    momentum: int
    contested: int
    bull_heat: float
    bear_heat: float
    n_bull: int
    n_bear: int
