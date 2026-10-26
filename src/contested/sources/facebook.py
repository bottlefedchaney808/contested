from __future__ import annotations

from ..models import RawPost, TimeWindow
from .base import SourceError


class FacebookSource:
    name = "facebook"

    def fetch(self, tickers, window: TimeWindow) -> list:
        raise SourceError("facebook: no access path in v1 (adapter stub)")
