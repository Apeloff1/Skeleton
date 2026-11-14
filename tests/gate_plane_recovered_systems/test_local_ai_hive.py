"""Loopback local-AI proxy against a real loopback HTTP server, and the Hive mount."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skeleton.gate_plane.systems.hive_mount import (
    MAX_WALK_PAYLOADS,
    HiveRequestError,
    build_hive_router,
    run_walk,
)
from skeleton.gate_plane.systems.local_ai_proxy import (
    OPERATIONS,
    LocalAIProxy,
    LocalAIProxyError,
    build_local_ai_router,
    sanitize_body,
)


class FakeRuntime(BaseHTTPRequestHandler):
    """Minimal llama.cpp-server-shaped loopback runtime."""

    seen: list = []
    mode = "ok"

    def _reply(self, status, obj=None, raw=None, extra=()):
        data = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        type(self).seen.append(("GET", self.path, None))
        if type(self).mode == "fail":
            return self._reply(500, {"error": "x"})
        if type(self).mode == "redirect":
            return self._reply(302, {}, extra=[("location", "http://example.com/")])
        if self.path == "/health":
            return self._reply(200, {"status": "ok"})
        if self.path == "/v1/models":
            return self._reply(200, {"data": [{"id": "Qwen3-0.6B-Q8_0"}]})
        return self._reply(404, {"error": "nf"})

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(n) or b"null")
        type(self).seen.append(("POST", self.path, body))
        if type(self).mode == "fail":
            return self._reply(500, {"error": "x"})
        if type(self).mode == "big":
            return self._reply(200, raw=b'{"x":"' + b"a" * 5000 + b'"}')
        if type(self).mode == "notjson":
            return self._reply(200, raw=b"<html>")
        return self._reply(200, {"choices": [{"message": {"role": "assistant", "content": "hi"}}], "echo": body})

    def log_message(self, *a):
        pass


@pytest.fixture
def runtime():
    FakeRuntime.seen = []
    FakeRuntime.mode = "ok"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeRuntime)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


CHAT = {"messages": [{"role": "user", "content": "hello"}], "max_tokens": 99999, "stream": True}


def test_refuses_non_loopback():
    for host in ("10.0.0.5", "example.com", "0.0.0.0"):
        with pytest.raises(LocalAIProxyError):
            LocalAIProxy(host, 8080)
    with pytest.raises(LocalAIProxyError):
        LocalAIProxy("127.0.0.1", 70000)


def test_sanitize_body():
    chat = OPERATIONS["chat"]
    out = sanitize_body(chat, CHAT, max_tokens=256)
    assert out["stream"] is False and out["max_tokens"] == 256
    assert sanitize_body(chat, {"messages": [{"role": "u", "content": "x"}]})["max_tokens"] == 1024
    for bad in (None, [], {"messages": []}, {"messages": [{"content": "x"}]}, {"messages": [{"role": "u", "content": "x"}], "max_tokens": 0}):
        with pytest.raises(LocalAIProxyError):
            sanitize_body(chat, bad)
    with pytest.raises(LocalAIProxyError):
        sanitize_body(OPERATIONS["complete"], {"prompt": 3})
    assert sanitize_body(OPERATIONS["complete"], {"prompt": "x", "n_predict": 5})["n_predict"] == 5


def test_chat_forwarded_sanitized(runtime):
    proxy = LocalAIProxy("127.0.0.1", runtime, max_tokens=128)
    res = proxy.call("chat", CHAT, service="jeeves-worker")
    assert res.status == 200 and res.body["choices"][0]["message"]["content"] == "hi"
    method, path, body = FakeRuntime.seen[-1]
    assert (method, path) == ("POST", "/v1/chat/completions")
    assert body["stream"] is False and body["max_tokens"] == 128


def test_read_operations_and_unknown(runtime):
    proxy = LocalAIProxy("localhost", runtime)
    assert proxy.call("health").body == {"status": "ok"}
    assert proxy.call("models").body["data"][0]["id"] == "Qwen3-0.6B-Q8_0"
    assert proxy.call("slots").status == 404
    assert proxy.call("chat", {"messages": []}).status == 400


def test_upstream_guards(runtime):
    proxy = LocalAIProxy("127.0.0.1", runtime, max_response_bytes=1000)
    FakeRuntime.mode = "big"
    assert proxy.call("chat", CHAT).body == {"error": "upstream_response_too_large"}
    FakeRuntime.mode = "notjson"
    assert proxy.call("chat", CHAT).body == {"error": "upstream_not_json"}
    FakeRuntime.mode = "redirect"
    assert proxy.call("health").body == {"error": "upstream_redirect_refused"}


def test_breaker_opens_on_repeated_failure(runtime):
    proxy = LocalAIProxy("127.0.0.1", runtime)
    FakeRuntime.mode = "fail"
    statuses = [proxy.call("chat", CHAT).status for _ in range(5)]
    assert statuses[:3] == [500, 500, 500]
    assert statuses[3] == 503 and "open" in proxy.breaker_states().values()
    FakeRuntime.mode = "ok"
    posts_before = sum(1 for m, _, _ in FakeRuntime.seen if m == "POST")
    assert proxy.call("chat", CHAT).status == 503
    assert sum(1 for m, _, _ in FakeRuntime.seen if m == "POST") == posts_before  # short-circuited


def test_unreachable_runtime():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeRuntime)
    port = srv.server_address[1]
    srv.server_close()
    res = LocalAIProxy("127.0.0.1", port).call("health")
    assert res.status in (502, 503, 504) and res.error


def test_local_ai_router(runtime):
    app = FastAPI()
    app.include_router(build_local_ai_router(LocalAIProxy("127.0.0.1", runtime)))
    c = TestClient(app)
    assert c.get("/api/v1/local-ai/health").json() == {"status": "ok"}
    assert c.post("/api/v1/local-ai/chat", content=b"{bad").status_code == 400
    r = c.post("/api/v1/local-ai/chat", json=CHAT)
    assert r.status_code == 200 and r.json()["echo"]["stream"] is False
    assert c.post("/api/v1/local-ai/complete", json={"prompt": "x"}).status_code == 200
    assert isinstance(c.get("/api/v1/local-ai/admin/breakers").json(), dict)


def test_run_walk_bounds():
    out = run_walk(["a", "b", "c"])
    assert out["n"] == 3 and out["kind"] == "walk"
    assert run_walk([f"n{i}" for i in range(20)])["n"] == 8  # Hive WALK_CAP
    for bad in (None, [], [1], [""], ["x" * 300], ["a"] * (MAX_WALK_PAYLOADS + 1)):
        with pytest.raises(HiveRequestError):
            run_walk(bad)


def test_hive_router():
    app = FastAPI()
    app.include_router(build_hive_router())
    c = TestClient(app)
    cap = c.get("/api/v1/hive/capabilities").json()
    assert cap["contract"]["chain"] == 0 and cap["contract"]["walk_cap"] == 8
    v = c.get("/api/v1/hive/verify")
    assert v.status_code == 200 and v.json()["ok"] == 1
    assert c.post("/api/v1/hive/snapshot").json()["hit"] == 1
    assert c.post("/api/v1/hive/walk", json={"payloads": ["a", "b"]}).json()["n"] == 2
    assert c.post("/api/v1/hive/walk", json={"payloads": []}).status_code == 400
    assert c.post("/api/v1/hive/walk", json=[1]).status_code == 400
    assert c.post("/api/v1/hive/walk", content=b"{").status_code == 400
