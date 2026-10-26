from datetime import datetime, timezone

from contested.models import RawPost
from contested.normalizer import extract_tickers, normalize_posts

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
SET = frozenset({"GME", "AMC", "MMM", "GOOGL"})


def test_extract_cashtag():
    assert extract_tickers("going long $GME", SET) == ("GME",)


def test_extract_bare_mention():
    assert extract_tickers("GME is ripping", SET) == ("GME",)


def test_extract_multiple_ordered_unique():
    assert extract_tickers("$GME then AMC and $GME again", SET) == ("GME", "AMC")


def test_drops_non_us():
    assert extract_tickers("$TSM and $700", SET) == ()


def test_bare_short_word_ignored():
    # len < 3 bare mention should not match
    assert extract_tickers("AMC MMM GOOGL", SET) == ("AMC", "MMM", "GOOGL")


def test_word_boundary():
    # substring of a longer word should not match
    assert extract_tickers("the gamestop store", SET) == ()


def test_normalize_drops_no_ticker():
    r = RawPost("t", "1", "a", "no ticker here", NOW)
    assert normalize_posts([r], SET) == []


def test_normalize_classifies_and_weights():
    r = RawPost("t", "1", "a", "LONG $GME to the moon", NOW, upvotes=9)
    evs = normalize_posts([r], SET)
    assert len(evs) == 1
    e = evs[0]
    assert e.tickers == ("GME",)
    assert e.sentiment == "bull"
    assert e.engagement == 1.0  # log10(1+9)
    assert e.intensity >= 1.0
