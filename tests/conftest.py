import pytest
from datetime import datetime, timezone

from contested.models import RawPost, TimeWindow

# Test "now": real current time truncated to seconds. Dynamic so the CLI/e2e
# tests (which scan with the real utcnow()) keep passing at any future date;
# the store round-trips timestamps with second precision.
NOW = datetime.now(timezone.utc).replace(microsecond=0)


class FakeSource:
    def __init__(self, name, posts=None, error=None):
        self.name = name
        self._posts = posts or []
        self._error = error
        self.last_tickers = None

    def fetch(self, tickers, window: TimeWindow):
        self.last_tickers = list(tickers)
        if self._error:
            raise self._error
        return list(self._posts)


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def ticker_set():
    return frozenset({"GME", "AMC", "MMM"})
