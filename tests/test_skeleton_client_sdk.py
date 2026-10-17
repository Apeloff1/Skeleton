"""Tests for the app-foundation client SDK (auth, agents, builds, streaming)."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from skeleton.client import (
    AgentsClient,
    AuthClient,
    BuildsClient,
    CancelToken,
    GatewayClient,
    RetryPolicy,
    SkeletonCancelledError,
    SkeletonClientError,
    SkeletonHTTPError,
    StreamEvent,
)
from skeleton.client import agents as agents_mod
from skeleton.client import auth as auth_mod
from skeleton.client import builds as builds_mod
from skeleton.client.streaming import parse_sse_lines


def _gw(handler, *, sleeps=None, retry=None, headers=None):
    sleeps = sleeps if sleeps is not None else []
    return GatewayClient(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler), headers=headers or {}),
        retry=retry or RetryPolicy(max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=1.0),
        sleep=sleeps.append,
    )


# --- backoff / Retry-After / cancellation -----------------------------------

def test_backoff_sleeps_between_idempotent_retries():
    hits = []
    sleeps: list[float] = []

    def handler(req):
        hits.append(1)
        return httpx.Response(503 if len(hits) < 3 else 200, json={"ok": True})

    assert _gw(handler, sleeps=sleeps).health() == {"ok": True}
    assert len(hits) == 3
    policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=1.0)
    assert sleeps == [policy.delay_for_attempt(0), policy.delay_for_attempt(1)]


def test_non_idempotent_never_sleeps_or_retries():
    sleeps: list[float] = []
    gw = _gw(lambda r: httpx.Response(503, json={}), sleeps=sleeps)
    with pytest.raises(SkeletonHTTPError):
        AgentsClient(gw).register(["code"])
    assert sleeps == []


def test_retry_after_header_honoured_and_bounded():
    hits = []
    sleeps: list[float] = []

    def handler(req):
        hits.append(1)
        if len(hits) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.5"})
        if len(hits) == 2:
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, json={})

    _gw(handler, sleeps=sleeps).health()
    assert sleeps == [pytest.approx(0.5), pytest.approx(1.0)]


def test_retry_exhaustion_raises_last_error():
    sleeps: list[float] = []
    with pytest.raises(SkeletonHTTPError) as info:
        _gw(lambda r: httpx.Response(502), sleeps=sleeps).health()
    assert info.value.status_code == 502
    assert len(sleeps) == 2


def test_cancel_before_attempt():
    tok = CancelToken()
    tok.cancel("stop")
    gw = _gw(lambda r: pytest.fail("should not send"))
    with pytest.raises(SkeletonCancelledError, match="stop"):
        AgentsClient(gw).get_task("t1", cancel=tok)
    assert issubclass(SkeletonCancelledError, SkeletonClientError)


def test_cancel_during_retry_sleep():
    tok = CancelToken()
    hits = []

    def handler(req):
        hits.append(1)
        return httpx.Response(503)

    gw = GatewayClient(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)),
        sleep=lambda d: tok.cancel(),
    )
    with pytest.raises(SkeletonCancelledError):
        AgentsClient(gw).get_task("t1", cancel=tok)
    assert len(hits) == 1


def test_cancel_token_real_clock_wait_is_interruptible():
    tok = CancelToken()
    tok.cancel()
    assert tok.wait(5) is True and tok.cancelled


# --- auth ---------------------------------------------------------------------

def test_auth_client_paths_and_callback_not_retried():
    seen = []
    sleeps: list[float] = []

    def handler(req):
        seen.append((req.method, req.url.path, dict(req.url.params)))
        if req.url.path.endswith("/callback"):
            return httpx.Response(503)
        return httpx.Response(200, json={"path": req.url.path})

    auth = AuthClient(_gw(handler, sleeps=sleeps))
    auth.github_oauth_card()
    auth.github_start()
    auth.tokens_audit()
    auth.token_audit("tok/1")
    auth.authz_audit()
    auth.authz_audit_row("deploy")
    with pytest.raises(SkeletonHTTPError):
        auth.github_callback("abc", state="s")
    paths = [p for _, p, _ in seen]
    assert "/api/v1/auth/github" in paths
    assert "/api/v1/application/tokens/audit/tok%2F1" in [str(httpx.URL("http://t" + p).raw_path.decode()) for p in paths] or "/api/v1/application/tokens/audit/tok/1" in paths
    assert seen[-1][2] == {"code": "abc", "state": "s"}
    assert sleeps == []
    with pytest.raises(ValueError):
        auth.github_callback("")


# --- agents -------------------------------------------------------------------

def test_agents_client_calls():
    seen = []

    def handler(req):
        body = json.loads(req.content) if req.content else None
        seen.append((req.method, req.url.path, body, dict(req.url.params)))
        if req.url.path == "/api/v1/swarm/agent":
            return httpx.Response(200, json={"agent_id": "a1", "status": "registered"})
        if req.url.path == "/api/v1/swarm/events":
            return httpx.Response(200, json={"events": [{"timestamp": 1.0, "kind": "submit", "subject": "t1"}]})
        return httpx.Response(200, json={"id": "x"})

    agents = AgentsClient(_gw(handler))
    assert agents.register(["code"], weight=2.0, metadata={"k": 1})["agent_id"] == "a1"
    assert seen[0][2] == {"specialisations": ["code"], "weight": 2.0, "metadata": {"k": 1}}
    agents.register_worker("w1", capabilities=["py"], capacity=2)
    assert seen[-1][2] == {"worker_id": "w1", "capabilities": ["py"], "capacity": 2}
    agents.heartbeat("w1")
    agents.unregister_worker("w1", requeue=False)
    assert seen[-1][:2] == ("DELETE", "/api/v1/swarm/workers/w1") and seen[-1][3] == {"requeue": "false"}
    agents.submit_task("t1", {"a": 1}, priority=5)
    agents.cancel_task("t1", "nope")
    assert seen[-1][2] == {"reason": "nope"}
    agents.revive_task("t1", reset_attempts=True)
    agents.list_tasks(state="queued")
    assert seen[-1][3]["state"] == "queued"
    assert agents.events(limit=5)[0]["kind"] == "submit"
    evs = list(agents.stream_events())
    assert evs[0].ts == 1.0 and evs[0].raw["subject"] == "t1"


# --- builds -------------------------------------------------------------------

ENGINE_SNAPSHOT = {
    "execution_id": "e1",
    "events": [
        {"event_id": "execution:e1:state", "sequence": 0, "type": "execution.state", "state": "running"},
        {"event_id": "turn:t1", "sequence": 1, "type": "execution.turn", "turn": {}},
    ],
    "next_sequence": 2,
}


def test_builds_client_scoped_calls_and_headers():
    seen = []

    def handler(req):
        body = json.loads(req.content) if req.content else None
        seen.append((req.method, req.url.path, body, dict(req.url.params), req.headers))
        if req.url.path.endswith("/events"):
            return httpx.Response(200, json=ENGINE_SNAPSHOT)
        if req.method == "POST" and req.url.path == "/api/v1/engine/executions":
            return httpx.Response(202, json={"execution_id": "e1", "state": "accepted"})
        return httpx.Response(200, json={"execution_state": "running"})

    hdrs = BuildsClient.service_headers("tok", "svc")
    builds = BuildsClient(_gw(handler, headers=hdrs), actor_id="u", tenant_id="t")
    assert builds.submit({"op": 1})["execution_id"] == "e1"
    assert seen[0][2] == {"actor_id": "u", "tenant_id": "t", "command": {"op": 1}}
    assert seen[0][4]["authorization"] == "Bearer tok" and seen[0][4]["x-zaibatsu-attester"] == "svc"
    builds.status("e1")
    assert seen[-1][3] == {"actor_id": "u", "tenant_id": "t"}
    builds.handoff("e1")
    builds.cancel("e1", "user abort")
    assert seen[-1][2]["reason"] == "user abort"
    assert builds.events("e1")["next_sequence"] == 2
    evs = list(builds.stream_execution_events("e1"))
    assert [e.type for e in evs] == ["execution.state", "execution.turn"]
    assert evs[1].id == "turn:t1" and evs[1].sequence == 1
    with pytest.raises(ValueError):
        BuildsClient(_gw(handler), actor_id="", tenant_id="t")


def test_builds_wait_polls_until_terminal_and_cancel():
    states = iter(["queued", "running", "completed"])
    naps: list[float] = []
    gw = _gw(lambda r: httpx.Response(200, json={"execution_state": next(states)}))
    builds = BuildsClient(gw, actor_id="u", tenant_id="t")
    assert builds.wait("e1", poll_seconds=0.5, sleep=naps.append)["execution_state"] == "completed"
    assert naps == [0.5, 0.5]

    tok = CancelToken()
    gw2 = _gw(lambda r: httpx.Response(200, json={"execution_state": "running"}))
    with pytest.raises(SkeletonCancelledError):
        BuildsClient(gw2, actor_id="u", tenant_id="t").wait("e1", cancel=tok, sleep=lambda s: tok.cancel())


# --- streaming ---------------------------------------------------------------

SSE_BODY = (
    ": keep-alive\n\n"
    "id: 7\nevent: progress\ndata: {\"v\":1,\"id\":\"ev7\",\"ts\":\"2026-10-17T16:00:00Z\",\"channel\":\"build\","
    "\"type\":\"build.progress\",\"payload\":{\"pct\":40},\"job_id\":\"e1\",\"correlation_id\":\"c1\"}\n\n"
    "data: {\"type\":\"heartbeat\"}\n\n"
    "event: heartbeat\ndata: ping\n\n"
    "id: 8\ndata: {\"type\":\"execution.result\",\n"
    "data: \"sequence\":3}\n\n"
)


def test_sse_stream_envelope_heartbeats_and_last_event_id():
    seen_headers = []

    def handler(req):
        seen_headers.append(req.headers)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=SSE_BODY.encode())

    builds = BuildsClient(_gw(handler), actor_id="u", tenant_id="t")
    evs = list(builds.stream_execution_events("e1", last_event_id="6"))
    assert seen_headers[0]["last-event-id"] == "6"
    assert len(evs) == 2
    first = evs[0]
    assert first.is_envelope_v1 and first.channel == "build" and first.v == 1
    assert first.payload == {"pct": 40} and first.job_id == "e1" and first.correlation_id == "c1"
    assert first.id == "ev7" and first.sse_id == "7" and first.sse_event == "progress"
    assert evs[1].type == "execution.result" and evs[1].sequence == 3 and evs[1].id == "8"
    assert not evs[1].is_envelope_v1


def test_sse_control_events_surface_and_hb_comment_skipped():
    body = (
        ": hb\n\n"
        "id: 10\nevent: stream.lagged\ndata: {\"v\":1,\"id\":\"10\",\"channel\":\"build\",\"type\":\"stream.lagged\",\"payload\":{\"dropped\":4}}\n\n"
        ": hb\n\n"
        "event: stream.reset\ndata: {\"type\":\"stream.reset\"}\n\n"
    )
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())

    evs = list(BuildsClient(_gw(handler), actor_id="u", tenant_id="t").stream_execution_events("e1", cursor="9"))
    assert [e.type for e in evs] == ["stream.lagged", "stream.reset"]
    assert all(e.is_control for e in evs) and evs[0].payload == {"dropped": 4} and evs[0].id == "10"
    assert seen[0].url.params["cursor"] == "9" and "last-event-id" not in seen[0].headers


def test_ndjson_is_not_a_stream_format_plain_list_still_ok():
    gw = _gw(lambda r: httpx.Response(200, json=[{"type": "x"}, {"type": "heartbeat"}]))
    assert [e.type for e in BuildsClient(gw, actor_id="u", tenant_id="t").stream_execution_events("e1")] == ["x"]
    import skeleton.client.streaming as st
    assert not hasattr(st, "parse_ndjson_lines")


def test_stream_cancel_between_events():
    tok = CancelToken()
    lines = ['data: {"type":"a"}', "", 'data: {"type":"b"}', ""]
    out = []
    with pytest.raises(SkeletonCancelledError):
        for ev in parse_sse_lines(lines, tok):
            out.append(ev)
            tok.cancel()
    assert [e.type for e in out] == ["a"]


def test_stream_retries_retryable_status_then_raises_http_error():
    hits = []
    sleeps: list[float] = []

    def handler(req):
        hits.append(1)
        if len(hits) == 1:
            return httpx.Response(503, headers={"Retry-After": "0.3"})
        return httpx.Response(404, json={"detail": "unknown execution"})

    with pytest.raises(SkeletonHTTPError) as info:
        list(BuildsClient(_gw(handler, sleeps=sleeps), actor_id="u", tenant_id="t").stream_execution_events("e1"))
    assert info.value.status_code == 404 and sleeps == [pytest.approx(0.3)]


def test_stream_event_fallback_raw():
    ev = StreamEvent.from_obj("hello")
    assert ev.raw == {"data": "hello"} and ev.type is None


# --- route conformance (static, via individual APIRouter objects) ------------

def _backend_routes() -> set[tuple[str, str]]:
    from skeleton.api.engine_routes import router as engine_router
    from skeleton.api.routes import router as main_router
    from skeleton.api.swarm_routes import router as swarm_router

    out: set[tuple[str, str]] = set()
    for router in (main_router, engine_router, swarm_router):  # all mounted at /api/v1
        for route in router.routes:
            for method in getattr(route, "methods", None) or ():
                out.add((method, "/api/v1" + route.path))
    return out


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


@pytest.mark.parametrize(
    "method,path",
    list(auth_mod.SDK_ROUTES) + list(agents_mod.SDK_ROUTES) + list(builds_mod.SDK_ROUTES),
)
def test_sdk_routes_exist_in_backend(method, path):
    backend = {(m, _norm(p)) for m, p in _backend_routes()}
    assert (method, _norm(path)) in backend, f"{method} {path} not served by backend"


def test_sdk_route_tables_match_calls():
    """Every path the clients actually hit is declared in SDK_ROUTES."""
    declared = {(m, _norm(p)) for m, p in auth_mod.SDK_ROUTES + agents_mod.SDK_ROUTES + builds_mod.SDK_ROUTES}
    seen: set[tuple[str, str]] = set()

    def handler(req):
        seen.add((req.method, req.url.path))
        return httpx.Response(200, json={"events": [], "execution_state": "completed", "agent_id": "a", "status": "ok"})

    gw = _gw(handler)
    a, ag, b = AuthClient(gw), AgentsClient(gw), BuildsClient(gw, actor_id="u", tenant_id="t")
    a.github_oauth_card(); a.github_start(); a.github_callback("c"); a.tokens_audit(); a.token_audit("X")
    a.authz_audit(); a.authz_audit_row("X")
    ag.register(["x"]); ag.mesh_stats(); ag.status(); ag.list_workers(); ag.register_worker("X")
    ag.get_worker("X"); ag.heartbeat("X"); ag.unregister_worker("X"); ag.list_tasks(); ag.submit_task("X")
    ag.get_task("X"); ag.cancel_task("X"); ag.revive_task("X"); ag.events(); list(ag.stream_events())
    b.submit({}); b.status("X"); b.handoff("X"); b.cancel("X"); b.events("X"); list(b.stream_execution_events("X"))
    b.wait("X")
    norm_seen = {(m, re.sub(r"/X(?=/|$)", "/{}", p)) for m, p in seen}
    assert norm_seen <= declared, norm_seen - declared
    assert len(norm_seen) == len(declared)


# --- retry defaults (TD review) ---------------------------------------------

@pytest.mark.parametrize("call", [
    lambda gw: gw._json("GET", "/api/v1/x"),
    lambda gw: gw.request_raw("GET", "/api/v1/x"),
    lambda gw: gw.retrieval_query({}),
    lambda gw: AgentsClient(gw).heartbeat("w"),
    lambda gw: BuildsClient(gw, actor_id="u", tenant_id="t").submit({}),
    lambda gw: BuildsClient(gw, actor_id="u", tenant_id="t").cancel("e"),
])
def test_requests_not_retried_by_default(call):
    hits = []
    sleeps: list[float] = []

    def handler(req):
        hits.append(1)
        return httpx.Response(503, json={})

    try:
        call(_gw(handler, sleeps=sleeps))
    except SkeletonHTTPError:
        pass
    assert len(hits) == 1 and sleeps == []


def test_backoff_uses_delay_for_attempt_exactly():
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=0.05, max_delay_seconds=0.15)
    sleeps: list[float] = []
    with pytest.raises(SkeletonHTTPError):
        _gw(lambda r: httpx.Response(500), sleeps=sleeps, retry=policy).health()
    assert sleeps == [policy.delay_for_attempt(n) for n in range(3)]


# --- request seal (docs/contracts/request_seal.md) ---------------------------

from skeleton.client import RequestSealer, SkeletonSealConfigError  # noqa: E402


def _verify(token, now):
    from skeleton.api.hmac_seal import verify_seal

    return verify_seal(token, now=now)


@pytest.mark.parametrize("principal", [None, "user42"])
def test_seal_roundtrip_with_real_verify_seal(monkeypatch, principal):
    monkeypatch.setenv("GF_SEAL_SECRET", "test-only-secret")
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    sealer = RequestSealer("sdk", principal=principal, clock=lambda: 1_000_000.0)
    token = sealer.token()
    assert token.count(".") == (3 if principal else 2)
    assert _verify(token, 1_000_299) == "sdk"
    from skeleton.api.middleware import AuthError

    with pytest.raises(AuthError):
        _verify(token, 1_000_301)  # absolute expiry, no skew
    assert "test-only-secret" not in repr(sealer) and token not in repr(sealer)


def test_seal_explicit_secret_and_missing_secret(monkeypatch):
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    with pytest.raises(SkeletonSealConfigError) as info:
        RequestSealer("sdk").token()
    assert issubclass(SkeletonSealConfigError, SkeletonClientError)
    tok = RequestSealer("sdk", seal_secret="explicit", clock=lambda: 100.0).token()
    from skeleton.api.hmac_seal import verify_seal

    assert verify_seal(tok, secret="explicit", now=150) == "sdk"
    assert "explicit" not in str(info.value)
    with pytest.raises(SkeletonSealConfigError):
        RequestSealer("bad.attester", seal_secret="x")


def test_seal_cached_and_reminted_30s_before_expiry():
    now = [1000.0]
    sealer = RequestSealer("sdk", seal_secret="s", clock=lambda: now[0])
    first = sealer.token()
    now[0] = 1000 + 269
    assert sealer.token() == first
    now[0] = 1000 + 270
    assert sealer.token() != first


def test_gateway_sends_seal_and_single_request_id():
    seen = []

    def handler(req):
        seen.append(req.headers)
        return httpx.Response(200, json={}, headers={"x-request-id": "echoed-1"})

    gw = GatewayClient(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)),
        seal_attester="sdk", seal_secret="s",
    )
    MemoryClientCheck = gw._json("POST", "/api/v1/memory/query", json={})
    assert MemoryClientCheck == {}
    h = seen[0]
    assert h["x-gf-seal"].startswith("sdk.") and len(h.get_list("x-request-id")) == 1
    assert gw.last_request_id == "echoed-1"
    with pytest.raises(ValueError):
        gw._call_headers("bad id!")


def test_seal_unavailable_503_never_retried():
    hits = []
    sleeps: list[float] = []

    def handler(req):
        hits.append(1)
        return httpx.Response(503, json={"error": "seal_unavailable"})

    gw = _gw(handler, sleeps=sleeps)
    with pytest.raises(SkeletonSealConfigError):
        gw.health()  # idempotent GET, still not retried
    with pytest.raises(SkeletonSealConfigError):
        list(AgentsClient(gw).stream_events())
    assert len(hits) == 2 and sleeps == []


def test_invalid_seal_401_reminted_once_then_raises():
    tokens = []

    def handler(req):
        tokens.append(req.headers["x-gf-seal"])
        return httpx.Response(401, json={"error": "invalid_seal"})

    now = [5000.0]
    sealer = RequestSealer("sdk", seal_secret="s", clock=lambda: now.__setitem__(0, now[0] + 1) or now[0])
    gw = GatewayClient(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)),
        seal=sealer, sleep=lambda d: None,
    )
    with pytest.raises(SkeletonHTTPError) as info:
        gw._json("POST", "/api/v1/commands/invoke", json={})
    assert info.value.status_code == 401 and len(tokens) == 2 and tokens[0] != tokens[1]

    ok = []

    def handler2(req):
        ok.append(1)
        return httpx.Response(401 if len(ok) == 1 else 200, json={"error": "invalid_seal"} if len(ok) == 1 else {"ok": 1})

    gw2 = GatewayClient(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler2)),
        seal_attester="sdk", seal_secret="s",
    )
    assert gw2._json("POST", "/api/v1/commands/invoke", json={}) == {"ok": 1}


# --- TD pre-merge fixes ------------------------------------------------------

from skeleton.client import MemoryClient, ServicesClient  # noqa: E402


def test_memory_query_unified_sends_top_k():
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json={})

    mem = MemoryClient(_gw(handler))
    mem.query_unified("q", top_k=5)
    mem.query_unified("q", limit=4)  # alias
    mem.query_unified("q")
    assert bodies == [{"query": "q", "top_k": 5}, {"query": "q", "top_k": 4}, {"query": "q"}]
    assert all("limit" not in b for b in bodies)
    with pytest.raises(ValueError):
        mem.query_unified("q", top_k=1, limit=2)


def test_services_execute_quotes_command_segment():
    raw = []

    def handler(req):
        raw.append(req.url.raw_path.decode())
        return httpx.Response(200, json={})

    svc = ServicesClient(_gw(handler))
    svc.execute("forge/build now")
    assert raw == ["/api/v1/commands/execute/forge%2Fbuild%20now"]


def test_builds_wait_default_timeout_and_validation():
    import inspect

    gw = _gw(lambda r: httpx.Response(200, json={"execution_state": "running"}))
    builds = BuildsClient(gw, actor_id="u", tenant_id="t")
    assert inspect.signature(builds.wait).parameters["timeout_seconds"].default == 600.0
    for bad in (None, 0, -1):
        with pytest.raises(ValueError):
            builds.wait("e1", timeout_seconds=bad)
    t = [0.0]
    with pytest.raises(SkeletonClientError):
        builds.wait("e1", poll_seconds=100, sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
    assert t[0] >= 600


def test_gateway_default_base_url_is_backend_port_8010():
    gw = GatewayClient()
    try:
        assert gw._base == "http://127.0.0.1:8010"
    finally:
        gw.close()
