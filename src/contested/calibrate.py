from __future__ import annotations

import math
from datetime import datetime

from .config import Config, ConfigError
from .models import utcnow
from .scorer import score_ticker
from .store import Store


def calibrate(store: Store, ticker_set, cfg: Config, low_ticker: str, high_ticker: str, now=None) -> tuple:
    now = now or utcnow()
    wh = cfg.scores.window_hours()
    events = store.events_in_window(now, wh)

    def raw(t):
        s = score_ticker(events, t, now, wh, cfg.scores.half_life_hours, 0.0, 1.0, cfg.scores.contested_floor)
        return s.bull_heat + s.bear_heat

    r_low = raw(low_ticker)
    r_high = raw(high_ticker)
    if r_high <= r_low:
        raise ConfigError(
            f"high anchor {high_ticker} raw ({r_high:.2f}) must exceed "
            f"low anchor {low_ticker} raw ({r_low:.2f})"
        )
    return math.log10(1.0 + r_low), math.log10(1.0 + r_high)
