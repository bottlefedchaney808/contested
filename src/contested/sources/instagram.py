from __future__ import annotations

from ..models import RawPost, TimeWindow
from .base import SourceError


class InstagramSource:
    name = "instagram"

    def fetch(self, tickers, window: TimeWindow) -> list:
        raise SourceError("instagram: no access path in v1 (adapter stub)")
