from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    pass


_WINDOW_RE = re.compile(r"^(\d+)([smhdw])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(spec: str) -> int:
    m = _WINDOW_RE.match(spec.strip().lower())
    if not m:
        raise ConfigError(f"invalid duration {spec!r}; use e.g. '15m', '1h', '7d'")
    n, unit = int(m.group(1)), m.group(2)
    return max(1, n * _UNIT_SECONDS[unit])


def parse_window(spec: str) -> int:
    return max(1, int(round(parse_duration(spec) / 3600.0)))


@dataclass
class SourceCfg:
    enabled: bool = True
    subs: list = field(default_factory=lambda: ["wallstreetbets", "stocks", "investing", "Options"])
    base_url: str = ""
    board: str = "biz"


@dataclass
class ScoresCfg:
    window: str = "7d"
    half_life_hours: float = 48.0
    l_low: float = 1.0
    l_high: float = 7.0
    contested_floor: float = 1.0

    def window_hours(self) -> int:
        return parse_window(self.window)


@dataclass
class Config:
    sources: dict = field(default_factory=dict)
    scores: ScoresCfg = field(default_factory=ScoresCfg)
    watchlist_path: str = "data/watchlist.txt"
    db_path: str = "data/contested.db"


def _source_cfg(raw: dict) -> SourceCfg:
    return SourceCfg(
        enabled=bool(raw.get("enabled", True)),
        subs=list(raw.get("subs", ["wallstreetbets", "stocks", "investing", "Options"])),
        base_url=str(raw.get("base_url", "")),
        board=str(raw.get("board", "biz")),
    )


def _scores_cfg(raw: dict) -> ScoresCfg:
    cfg = ScoresCfg(
        window=str(raw.get("window", "7d")),
        half_life_hours=float(raw.get("half_life_hours", 48.0)),
        l_low=float(raw.get("l_low", 1.0)),
        l_high=float(raw.get("l_high", 7.0)),
        contested_floor=float(raw.get("contested_floor", 1.0)),
    )
    if cfg.half_life_hours <= 0:
        raise ConfigError("scores.half_life_hours must be > 0")
    if cfg.l_high <= cfg.l_low:
        raise ConfigError("scores.l_high must be > scores.l_low")
    if cfg.contested_floor < 0:
        raise ConfigError("scores.contested_floor must be >= 0")
    parse_window(cfg.window)
    return cfg


def resolve_config_path(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit)
    cwd = Path.cwd() / "contested.toml"
    if cwd.is_file():
        return cwd
    return Path.home() / ".config" / "contested" / "contested.toml"


def load_config(path: str | Path | None = None) -> Config:
    p = resolve_config_path(path)
    data: dict = {}
    if p.is_file():
        with open(p, "rb") as fh:
            data = tomllib.load(fh)
    sources = {name: _source_cfg(raw) for name, raw in data.get("sources", {}).items()}
    if not sources:
        sources = {
            "reddit": SourceCfg(enabled=True),
            "x_grok": SourceCfg(enabled=True),
            "stocktwits": SourceCfg(enabled=True),
            "fourchan": SourceCfg(enabled=True),
            "facebook": SourceCfg(enabled=False),
            "instagram": SourceCfg(enabled=False),
        }
    return Config(
        sources=sources,
        scores=_scores_cfg(data.get("scores", {})),
        watchlist_path=str(data.get("watchlist", {}).get("path", "data/watchlist.txt")),
        db_path=str(data.get("db", {}).get("path", "data/contested.db")),
    )


def load_watchlist(path: str | Path) -> list:
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        t = line.strip().upper()
        if t and not t.startswith("#"):
            out.append(t)
    return out
