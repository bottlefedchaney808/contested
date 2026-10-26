import json

from typer.testing import CliRunner

from conftest import FakeSource, NOW
from contested.cli import app
from contested.models import RawPost

runner = CliRunner()


def test_watch_once_then_scan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "tickers_us.txt").write_text("GME\nAMC\n", encoding="utf-8")
    (tmp_path / "data" / "watchlist.txt").write_text("GME\n", encoding="utf-8")

    # Patch build_sources to return in-process fakes (no network).
    import contested.cli as cli
    fakes = {
        "reddit": FakeSource("reddit", [
            RawPost("reddit", "1", "a", "long $GME to the moon", NOW, upvotes=1000),
        ]),
        "x_grok": FakeSource("x_grok", [
            RawPost("x_grok", "2", "b", "sell $GME", NOW, upvotes=1000),
        ]),
    }
    monkeypatch.setattr(cli, "build_sources", lambda cfg: fakes)

    r1 = runner.invoke(app, ["watch", "--once"], catch_exceptions=False)
    assert r1.exit_code == 0, r1.output
    assert "inserted=2" in r1.output

    r2 = runner.invoke(app, ["scan", "--json"], catch_exceptions=False)
    assert r2.exit_code == 0, r2.output
    data = json.loads(r2.output)
    tickers = [s["ticker"] for s in data["scores"]]
    assert "GME" in tickers
