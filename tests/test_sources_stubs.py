import pytest
from datetime import datetime, timezone

from contested.models import TimeWindow
from contested.sources.base import SourceError
from contested.sources.facebook import FacebookSource
from contested.sources.instagram import InstagramSource

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
W = TimeWindow(NOW, NOW)


def test_facebook_stub_raises():
    with pytest.raises(SourceError):
        FacebookSource().fetch(["GME"], W)


def test_instagram_stub_raises():
    with pytest.raises(SourceError):
        InstagramSource().fetch(["GME"], W)
