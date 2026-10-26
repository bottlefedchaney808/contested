"""Manual live smoke test: fetch one page from each enabled source.

Run:  python scripts/smoke_live.py
Requires network and, for x_grok, GROK_BASE_URL + GROK_API_KEY.
"""
import sys
from datetime import timedelta

from contested.config import load_config
from contested.models import TimeWindow, utcnow
from contested.sources import build_sources
from contested.sources.base import SourceError


def main() -> int:
    cfg = load_config()
    sources = build_sources(cfg)
    now = utcnow()
    window = TimeWindow(start=now - timedelta(hours=24), end=now)
    failures = 0
    for name, src in sorted(sources.items()):
        try:
            posts = src.fetch([], window)
            print(f"OK   {name:<10} {len(posts)} posts")
        except SourceError as e:
            failures += 1
            print(f"FAIL {name:<10} {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERR  {name:<10} {e!r}")
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
