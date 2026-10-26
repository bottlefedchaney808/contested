import httpx
import pytest

from contested.sources.base import SourceError, http_get_json


def test_get_json_success():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"a": 1})))
    assert http_get_json("http://x/y", client) == {"a": 1}


def test_get_json_retries_then_succeeds():
    calls = {"n": 0}
    def handler(r):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert http_get_json("http://x", client, backoff=0.0) == {"ok": True}
    assert calls["n"] == 2


def test_get_json_exhausts_retries():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(SourceError):
        http_get_json("http://x", client, retries=2, backoff=0.0)


def test_get_json_4xx_no_retry():
    calls = {"n": 0}
    def handler(r):
        calls["n"] += 1
        return httpx.Response(404)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(SourceError):
        http_get_json("http://x", client, retries=3, backoff=0.0)
    assert calls["n"] == 1  # no retry on 404
