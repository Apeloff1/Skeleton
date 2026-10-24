"""Tests for the standalone chat/agent/run --probe CLI (HTTP mocked)."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from skeleton.forge import api_client as ac
from skeleton.forge import standalone_cli as sc


class FakeHttp:
    def __init__(self, routes, base_url="http://test:1"):
        self.routes = routes
        self.base_url = base_url
        self.calls = []

    def _answer(self, method, path, body=None):
        self.calls.append((method, path, body))
        val = self.routes.get((method, path))
        if isinstance(val, Exception):
            raise val
        if val is None:
            raise ac.ApiClientError(f"HTTP 404 {path}", status=404)
        return val

    def get(self, path):
        return self._answer("GET", path)

    def post(self, path, body):
        return self._answer("POST", path, body)


def backend(routes):
    return ac.BackendClient(http=FakeHttp(routes))


THREAD = {"thread": {"thread_id": "t1", "version": 1}}


class FakeResp:
    def __init__(self, body: bytes, status=200):
        self._b = io.BytesIO(body)
        self.status = status

    def read(self, n=-1):
        return self._b.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_client_bearer_and_json(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["auth"] = req.get_header("Authorization")
        seen["url"] = req.full_url
        seen["data"] = req.data
        return FakeResp(b'{"ok": true}')

    monkeypatch.setenv("SKELETON_TOKEN", "tok")
    monkeypatch.setattr(ac.urllib.request, "urlopen", fake_urlopen)
    out = ac.HttpClient("http://h:1/").post("/x", {"a": 1})
    assert out == {"ok": True}
    assert seen["auth"] == "Bearer tok"
    assert seen["url"] == "http://h:1/x"
    assert json.loads(seen["data"]) == {"a": 1}


def test_http_client_no_token_no_header(monkeypatch):
    monkeypatch.delenv("SKELETON_TOKEN", raising=False)
    assert "Authorization" not in ac.HttpClient("http://h").headers()


def test_http_client_rejects_non_http_scheme():
    with pytest.raises(ac.ApiClientError):
        ac.HttpClient("file:///etc/passwd")


def test_http_client_http_error(monkeypatch):
    def boom(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 409, "conflict", {}, io.BytesIO(b"stale"))

    monkeypatch.setattr(ac.urllib.request, "urlopen", boom)
    with pytest.raises(ac.ApiClientError) as ei:
        ac.HttpClient("http://h", token="").get("/y")
    assert ei.value.status == 409 and "stale" in str(ei.value)


def test_http_client_non_json(monkeypatch):
    monkeypatch.setattr(ac.urllib.request, "urlopen", lambda r, timeout: FakeResp(b"<html>"))
    with pytest.raises(ac.ApiClientError):
        ac.HttpClient("http://h", token="").get("/")


def test_env_urls():
    assert ac.backend_url_from_env({}) == "http://127.0.0.1:8001"
    assert ac.backend_url_from_env({"SKELETON_BACKEND_URL": "http://b/"}) == "http://b"
    assert ac.backend_url_from_env({"BACKEND_URL": "http://a", "SKELETON_BACKEND_URL": "http://b"}) == "http://a"
    assert ac.middleware_url_from_env({}) == "http://127.0.0.1:8010"


def test_create_conversation_validates_shape():
    assert backend({("POST", "/api/v1/conversations"): THREAD}).create_conversation()["thread_id"] == "t1"
    with pytest.raises(ac.ApiClientError):
        backend({("POST", "/api/v1/conversations"): {"thread": {"thread_id": "t", "version": 0}}}).create_conversation()


def test_chat_body_and_validation():
    b = backend({("POST", "/api/ai/chat"): {"response": "hi"}})
    b.chat("hello", thread_id="t1", expected_thread_version=2, context={"k": 1}, response_mode="deferred")
    _, path, body = b.http.calls[-1]
    assert path == "/api/ai/chat"
    assert body["thread_id"] == "t1" and body["expected_thread_version"] == 2
    assert body["response_mode"] == "deferred" and body["context"] == {"k": 1}
    assert body["idempotency_key"] and "conversation_history" not in body
    for kw in ({"expected_thread_version": 0}, {"response_mode": "stream"}):
        args = {"thread_id": "t1", "expected_thread_version": 1, **kw}
        with pytest.raises(ac.ApiClientError):
            b.chat("x", **args)


def test_agent_and_system_paths():
    b = backend({("POST", "/api/agents/single/coder"): {"ok": 1},
                 ("POST", "/api/agents/run/sys1"): {"ok": 2}})
    assert b.run_agent("coder", "t")["ok"] == 1
    assert b.http.calls[-1][2] == {"task": "t", "context": {}, "language": "python"}
    assert b.run_system("sys1", "t", code="c", max_iterations=4)["ok"] == 2
    assert b.http.calls[-1][2] == {"task": "t", "code": "c", "language": "python", "max_iterations": 4}
    with pytest.raises(ac.ApiClientError):
        b.run_agent("../x", "t")


def test_middleware_falls_back_to_api_health():
    m = ac.MiddlewareClient(http=FakeHttp({("GET", "/api/health"): {"status": "ok"}}))
    assert m.health() == {"path": "/api/health", "status": "ok"}


def test_probe_fail_closed():
    good_b = backend({("GET", "/api/health"): {"status": "ok"}})
    bad_m = ac.MiddlewareClient(http=FakeHttp({}))
    res = ac.probe_apis(good_b, bad_m)
    assert res.ok is False and [c["ok"] for c in res.checks] == [True, False]
    good_m = ac.MiddlewareClient(http=FakeHttp({("GET", "/api/health/live"): {}}))
    assert ac.probe_apis(good_b, good_m).ok is True


def test_parse_usage_errors():
    with pytest.raises(sc.UsageError):
        sc.parse_chat_args([])
    with pytest.raises(sc.UsageError):
        sc.parse_chat_args(["hi", "--version", "2"])
    with pytest.raises(sc.UsageError):
        sc.parse_chat_args(["hi", "--context", "[1]"])
    with pytest.raises(sc.UsageError):
        sc.parse_agent_args(["task"])
    with pytest.raises(sc.UsageError):
        sc.parse_agent_args(["--agent", "a"])
    assert sc.parse_agent_args(["--list"]).list is True
    assert sc.parse_run_probe_args(["vision"]) is None


def test_run_chat_opens_thread_when_missing(capsys):
    b = backend({("POST", "/api/v1/conversations"): THREAD, ("POST", "/api/ai/chat"): {"response": "pong"}})
    assert sc.run_chat(["ping"], client=b) == 0
    assert [c[1] for c in b.http.calls] == ["/api/v1/conversations", "/api/ai/chat"]
    assert b.http.calls[1][2]["expected_thread_version"] == 1
    assert capsys.readouterr().out.strip() == "pong"


def test_run_chat_existing_thread_and_exit_codes(capsys):
    b = backend({("POST", "/api/ai/chat"): {"response": "x"}})
    assert sc.run_chat(["hi", "--thread", "t9", "--version", "3", "--json"], client=b) == 0
    assert [c[1] for c in b.http.calls] == ["/api/ai/chat"]
    assert json.loads(capsys.readouterr().out)["thread_id"] == "t9"
    assert sc.run_chat([], client=b) == 2
    assert sc.run_chat(["hi", "--thread", "t", "--version", "1"], client=backend({})) == 1


def test_run_agent_modes(capsys):
    b = backend({("GET", "/api/agents/roles"): {"roles": {"coder": {"name": "Coder", "role": "x"}}},
                 ("GET", "/api/agents/systems"): {"systems": {"s1": {}}},
                 ("POST", "/api/agents/single/coder"): {"result": "done"},
                 ("POST", "/api/agents/run/s1"): {"result": "sys"}})
    assert sc.run_agent(["--list"], client=b) == 0
    out = capsys.readouterr().out
    assert "coder" in out and "s1" in out
    assert sc.run_agent(["fix", "--agent", "coder"], client=b) == 0
    assert sc.run_agent(["fix", "--system", "s1", "--max-iterations", "2"], client=b) == 0
    assert b.http.calls[-1][2]["max_iterations"] == 2
    assert sc.run_agent(["fix", "--agent", "nope"], client=b) == 1
    assert sc.run_agent(["fix"], client=b) == 2


def test_run_probe_fall_through_and_codes(capsys):
    assert sc.run_probe(["a vision", "--era", "x"]) == sc.FALL_THROUGH
    good_b = backend({("GET", "/api/health"): {}})
    good_m = ac.MiddlewareClient(http=FakeHttp({("GET", "/api/health/live"): {}}))
    assert sc.run_probe(["--probe"], backend=good_b, middleware=good_m) == 0
    assert sc.run_probe(["--probe", "--json"], backend=good_b,
                        middleware=ac.MiddlewareClient(http=FakeHttp({}))) == 1
    assert json.loads(capsys.readouterr().out.split("\n", 2)[-1])["ok"] is False
    assert sc.run_probe(["--probe", "--bogus"]) == 2


def test_main_dispatch_wiring(monkeypatch):
    import skeleton.__main__ as m

    monkeypatch.setattr(sc, "run_chat", lambda rest: 11)
    monkeypatch.setattr(sc, "run_agent", lambda rest: 12)
    assert m.main(["chat", "x"]) == 11
    assert m.main(["agent", "--list"]) == 12
    monkeypatch.setattr(sc, "run_probe", lambda rest: sc.FALL_THROUGH)
    monkeypatch.setattr(m, "_cmd_gameforge_run", lambda rest: 13)
    assert m.main(["run", "v"]) == 13
    monkeypatch.setattr(sc, "run_probe", lambda rest: 0)
    assert m.main(["run", "--probe"]) == 0


def test_mirrors_identical():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("api_client.py", "standalone_cli.py"):
        assert (root / "forge" / name).read_bytes() == (root / "ai" / "forge" / name).read_bytes()
