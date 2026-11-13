"""RequestSealMiddleware must accept keyring-only (GF_SEAL_KEYRING) deployments."""

from __future__ import annotations

import asyncio

from starlette.responses import Response

from skeleton.api.hmac_seal import _sign_legacy
from skeleton.api.middleware import GatePolicy, RequestSealMiddleware


def _call(headers: list[tuple[bytes, bytes]]) -> int:
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(scope, receive, send) -> None:
        await Response(status_code=204)(scope, receive, send)

    scope = {
        "type": "http", "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/api/x", "raw_path": b"/api/x", "query_string": b"", "headers": headers,
        "client": ("127.0.0.1", 1), "server": ("testserver", 80),
    }
    stack = RequestSealMiddleware(app, policy=GatePolicy(open_prefixes=("/health",), domains=()))
    asyncio.run(stack(scope, receive, send))
    return next(m for m in sent if m["type"] == "http.response.start")["status"]


def test_keyring_only_valid_seal_passes(monkeypatch):
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    monkeypatch.setenv("GF_SEAL_KEYRING", "k1=ring-secret")
    import time
    exp = int(time.time()) + 60
    seal = f"ci.{exp}.{_sign_legacy('ci', exp, 'ring-secret')}"
    assert _call([(b"x-gf-seal", seal.encode())]) == 204


def test_keyring_only_bad_seal_is_401(monkeypatch):
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    monkeypatch.setenv("GF_SEAL_KEYRING", "k1=ring-secret")
    assert _call([(b"x-gf-seal", b"ci.1.deadbeef")]) == 401


def test_no_secret_no_keyring_is_503(monkeypatch):
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    assert _call([]) == 503
