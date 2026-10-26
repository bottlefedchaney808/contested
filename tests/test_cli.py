from datetime import timedelta

import pytest
from typer.testing import CliRunner

from conftest import NOW
from contested.cli import app
from contested.models import Event, Score
from contested.scorer import engagement_weight
from contested.store import Store

runner = CliRunner()


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "tickers_us.txt").write_text("GME\nAMC\nMMM\n", encoding="utf-8")
    store = Store(tmp_path / "data" / "contested.db")
    store.init()
    evs = [
        Event("t", "1", "a", "long $GME", NOW, "bull", 3.0, engagement_weight(1000, 0, 0), ("GME",), ""),
        Event("t", "2", "b", "sell $GME", NOW, "bear", 3.0, engagement_weight(1000, 0, 0), ("GME",), ""),
        Event("t", "3", "c", "long $AMC", NOW, "bull", 1.0, engagement_weight(9, 0, 0), ("AMC",), ""),
        Event("t", "4", "d", "sell $AMC", NOW, "bear", 1.0, engagement_weight(9, 0, 0), ("AMC",), ""),
    ]
    store.upsert_events(evs)
    store.save_score(Score("GME", NOW, 168, 90, 80, 10.0, 9.0, 2, 2))
    store.save_score(Score("AMC", NOW, 168, 20, 10, 1.0, 0.9, 1, 1))
    return tmp_path


def test_scan_prints_ranked(seeded):
    r = runner.invoke(app, ["scan", "--window", "7d", "--top", "10"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    out = r.output
    assert "GME" in out and "AMC" in out
    # GME ranks above AMC by momentum
    assert out.index("GME") < out.index("AMC")
    assert "sources:" in out


def test_scan_json(seeded):
    import json
    r = runner.invoke(app, ["scan", "--json"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["mode"] == "watch"
    assert data["scores"][0]["ticker"] == "GME"


def test_scan_requires_ticker_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["scan"], catch_exceptions=False)
    assert r.exit_code != 0
    assert "update-tickers" in r.output


def test_ticker_deep_dive(seeded):
    r = runner.invoke(app, ["ticker", "GME"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert "GME" in r.output
    assert "bull" in r.output.lower()


def test_sources_command(seeded):
    r = runner.invoke(app, ["sources"], catch_exceptions=False)
    assert r.exit_code == 0
    assert "reddit" in r.output


def test_sparkline_monotonic():
    from contested.cli import sparkline
    assert len(sparkline([1, 2, 3, 4])) == 4
