import pytest

from contested.config import Config, ConfigError, ScoresCfg, SourceCfg
from contested.sources import build_sources


def _cfg(**overrides):
    sources = {
        "reddit": SourceCfg(enabled=True),
        "x_grok": SourceCfg(enabled=True),
        "stocktwits": SourceCfg(enabled=True),
        "fourchan": SourceCfg(enabled=True),
        "facebook": SourceCfg(enabled=False),
        "instagram": SourceCfg(enabled=False),
    }
    sources.update(overrides)
    return Config(sources=sources, scores=ScoresCfg())


def test_build_includes_only_enabled(monkeypatch):
    monkeypatch.setenv("GROK_BASE_URL", "https://api.x.ai")
    monkeypatch.setenv("GROK_API_KEY", "k")
    built = build_sources(_cfg())
    assert set(built) == {"reddit", "x_grok", "stocktwits", "fourchan"}


def test_x_grok_requires_env(monkeypatch, tmp_path):
    monkeypatch.delenv("GROK_BASE_URL", raising=False)
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    monkeypatch.setenv("DSH_GROK_AUTH_FILE", str(tmp_path / "missing-auth.json"))
    with pytest.raises(ConfigError):
        build_sources(_cfg())


def test_unknown_source_rejected():
    with pytest.raises(ConfigError):
        build_sources(_cfg(bogus=SourceCfg(enabled=True)))
