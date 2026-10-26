from __future__ import annotations

import os

from ..config import Config, ConfigError
from .base import Source, SourceError
from .facebook import FacebookSource
from .fourchan import FourChanSource
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
            base_url = scfg.base_url or env.get("GROK_BASE_URL", "")
            api_key = env.get("GROK_API_KEY", "")
            if not base_url or not api_key:
                raise ConfigError(
                    "x_grok is enabled but GROK_BASE_URL and GROK_API_KEY env vars are required"
                )
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
