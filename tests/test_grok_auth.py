import json

import httpx
import pytest

from contested.config import ConfigError
from contested.sources.grok_auth import resolve_grok


def test_api_key_wins_over_stored_login(monkeypatch, tmp_path):
    monkeypatch.setenv("GROK_API_KEY", "explicit-key")
    monkeypatch.setenv("DSH_GROK_AUTH_FILE", str(tmp_path / "auth.json"))
    base, key = resolve_grok("", {"GROK_API_KEY": "explicit-key", "GROK_BASE_URL": "https://api.x.ai"})
    assert base == "https://api.x.ai"
    assert key == "explicit-key"


def test_missing_login_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("DSH_GROK_AUTH_FILE", str(tmp_path / "missing.json"))
    with pytest.raises(ConfigError):
        resolve_grok("https://api.x.ai", {})


def test_refresh_uses_stored_login_and_writes_back(monkeypatch, tmp_path):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({
        "grok": {
            "default": "me",
            "accounts": {
                "me": {
                    "accessToken": "stale",
                    "refreshToken": "refresh-me",
                    "expiresAt": 0,
                    "tokenEndpoint": "https://auth.x.ai/oauth2/token",
                }
            },
        }
    }), encoding="utf-8")
    monkeypatch.setenv("DSH_GROK_AUTH_FILE", str(path))

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert "grant_type=refresh_token" in body
        assert "refresh-me" in body
        return httpx.Response(200, json={
            "access_token": "fresh-access",
            "refresh_token": "fresh-refresh",
            "expires_in": 3600,
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    base, key = resolve_grok("", {}, client=client)
    assert base == "https://api.x.ai"
    assert key == "fresh-access"
    saved = json.loads(path.read_text(encoding="utf-8"))
    session = saved["grok"]["accounts"]["me"]
    assert session["accessToken"] == "fresh-access"
    assert session["refreshToken"] == "fresh-refresh"
    assert session["expiresAt"] > 0
