import pytest

from contested.config import (
    ConfigError,
    load_config,
    load_watchlist,
    parse_duration,
    parse_window,
    resolve_config_path,
)


def test_parse_window_days():
    assert parse_window("7d") == 168


def test_parse_window_hours():
    assert parse_window("24h") == 24


def test_parse_window_rounds_small_up():
    assert parse_window("30m") == 1


def test_parse_window_rejects_garbage():
    with pytest.raises(ConfigError):
        parse_window("7")


def test_parse_duration_minutes():
    assert parse_duration("15m") == 900


def test_parse_duration_hours():
    assert parse_duration("1h") == 3600


def test_load_config_defaults_without_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.scores.window == "7d"
    assert cfg.scores.l_high > cfg.scores.l_low
    assert cfg.sources["facebook"].enabled is False
    assert cfg.sources["reddit"].enabled is True
    assert cfg.watchlist_path == "data/watchlist.txt"
    assert cfg.db_path == "data/contested.db"


def test_load_config_reads_file(tmp_path):
    p = tmp_path / "contested.toml"
    p.write_text(
        '[scores]\nwindow = "24h"\nl_low = 0.5\nl_high = 3.0\n'
        '[sources.x_grok]\nenabled = false\n'
        '[watchlist]\npath = "wl.txt"\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.scores.window_hours() == 24
    assert cfg.sources["x_grok"].enabled is False
    assert cfg.watchlist_path == "wl.txt"


def test_load_config_rejects_bad_band(tmp_path):
    p = tmp_path / "contested.toml"
    p.write_text('[scores]\nl_low = 5.0\nl_high = 5.0\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)


def test_load_watchlist(tmp_path):
    p = tmp_path / "wl.txt"
    p.write_text("# comment\ngme\n\namc\n", encoding="utf-8")
    assert load_watchlist(p) == ["GME", "AMC"]


def test_load_watchlist_missing(tmp_path):
    assert load_watchlist(tmp_path / "nope.txt") == []


def test_resolve_config_path_explicit(tmp_path):
    p = tmp_path / "custom.toml"
    assert resolve_config_path(p) == p
