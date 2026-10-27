from __future__ import annotations

import os

from ..config import Config, ConfigError
from .base import Source, SourceError
from .facebook import FacebookSource
from .fourchan import FourChanSource
from .grok_auth import resolve_grok
from .instagram import InstagramSource
from .reddit import RedditSource
from .stocktwits import StocktwitsSource
from .x_grok import XGrokSource

__all__ = ["build_sources", "Source", "SourceError"]


def build_sources(cfg: Config) -> dict:
    env = os.environ
    out = {}
    for name, scfg in cfg.sources.items():
        if not scfg.enabled:
            continue
        if name == "reddit":
            out[name] = RedditSource(
                client_id=env.get("REDDIT_CLIENT_ID", ""),
                client_secret=env.get("REDDIT_CLIENT_SECRET", ""),
                subs=tuple(scfg.subs),
            )
        elif name == "x_grok":
            base_url, api_key = resolve_grok(scfg.base_url or "", env)
            out[name] = XGrokSource(base_url=base_url, api_key=api_key)
        elif name == "stocktwits":
            out[name] = StocktwitsSource()
        elif name == "fourchan":
            out[name] = FourChanSource(board=scfg.board)
        elif name == "facebook":
            out[name] = FacebookSource()
        elif name == "instagram":
            out[name] = InstagramSource()
        else:
            raise ConfigError(f"unknown source {name!r} in config")
    return out
