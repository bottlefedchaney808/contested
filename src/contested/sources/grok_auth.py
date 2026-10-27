"""Resolve a Grok bearer without printing or storing the token in the repo.

Order: GROK_API_KEY, then the OAuth session this machine already logged in
through DeepSeek Harness (~/.dsh/plugins/subscriptions/auth.json). The
refresh writes the renewed session back to that same file.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from ..config import ConfigError

# Public xAI OAuth client used by the Grok CLI login. Not a secret.
GROK_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
DEFAULT_BASE_URL = "https://api.x.ai"
_SKEW_MS = 60_000


def auth_file() -> Path:
    return Path(os.environ.get("DSH_GROK_AUTH_FILE") or Path.home() / ".dsh" / "plugins" / "subscriptions" / "auth.json")


def resolve_grok(base_url: str, env: dict | None = None, client: httpx.Client | None = None) -> tuple[str, str]:
    env = env if env is not None else os.environ
    base = (base_url or env.get("GROK_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    api_key = env.get("GROK_API_KEY", "")
    if api_key:
        return base, api_key
    return base, _access_token(client)


def _access_token(client: httpx.Client | None) -> str:
    path = auth_file()
    if not path.is_file():
        raise ConfigError(
            "x_grok is enabled but no GROK_API_KEY is set and no Grok login was found "
            f"at {path}. Log in through DeepSeek Harness, or set GROK_API_KEY."
        )
    store = json.loads(path.read_text(encoding="utf-8"))
    entry = store.get("grok") or {}
    accounts = entry.get("accounts") or {}
    key = entry.get("default") or next(iter(accounts), None)
    session = accounts.get(key) if key else None
    if not isinstance(session, dict) or not session.get("refreshToken"):
        raise ConfigError(f"x_grok: Grok login at {path} has no usable session. Log in again.")
    expires = int(session.get("expiresAt") or 0)
    access = session.get("accessToken") or ""
    if access and expires - _SKEW_MS > time.time() * 1000:
        return access
    return _refresh(path, store, key, session, client)


def _refresh(path: Path, store: dict, key: str, session: dict, client: httpx.Client | None) -> str:
    own = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        resp = client.post(
            session.get("tokenEndpoint") or "https://auth.x.ai/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": GROK_CLIENT_ID,
                "refresh_token": session["refreshToken"],
            },
        )
    finally:
        if own:
            client.close()
    if resp.status_code != 200:
        raise ConfigError(
            f"x_grok: Grok login refresh failed (HTTP {resp.status_code}). "
            "Log in again through DeepSeek Harness, or set GROK_API_KEY."
        )
    tokens = resp.json()
    access = tokens.get("access_token") or ""
    if not access:
        raise ConfigError("x_grok: Grok token endpoint returned no access token.")
    session["accessToken"] = access
    if tokens.get("refresh_token"):
        session["refreshToken"] = tokens["refresh_token"]
    if isinstance(tokens.get("expires_in"), (int, float)):
        session["expiresAt"] = int(time.time() * 1000 + tokens["expires_in"] * 1000)
    store["grok"]["accounts"][key] = session
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return access
