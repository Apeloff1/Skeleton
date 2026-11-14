"""BuildsClient.stream_events over GET /api/v1/events via skeleton.client.realtime (#4128)."""

from __future__ import annotations

import re

import httpx
import pytest

from skeleton.client import (
    BuildsClient,
    CancelToken,
    EventsClient,
    GatewayClient,
    RequestSealer,
    RetryPolicy,
    SkeletonCancelledError,
    SkeletonSealConfigError,
)
from skeleton.client import events as events_mod
from skeleton.client.realtime import RealtimeAuthError, ReconnectBackoff
from skeleton.realtime import RealtimeHub
from skeleton.realtime.envelope import ControlEvent, RealtimeEvent
from skeleton.realtime.sse import format_sse

SECRET = "wire-test-secret"
TS = "2026-10-17T17:00:00.000Z"


async def _no_sleep(_delay):
    return None


def _opts(**kw):
    return {"backoff": ReconnectBackoff(rng=lambda lo, hi: 0.0), "sleep": _no_sleep, **kw}


def _gw(*, seal=None, sync_handler=None):
    handler = sync_handler or (lambda r: httpx.Response(200, json={"slo": {}, "hub": {}}))
    return GatewayClient(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)),
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=0.01, max_delay_seconds=0.02),
        sleep=lambda s: None, seal=seal,
    )


def _ev(i, job="e1", type_="build.progress", channel="build"):
    return RealtimeEvent(id=str(i), ts=TS, channel=channel, type=type_, payload={"i": i}, job_id=job)


def _sse_response(frames):
    body = ": hb\n\n" + "".join(format_sse(f) for f in frames)
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())


def _async_client(handler):
    async def ahandler(req):
        return handler(req)

    return httpx.AsyncClient(transport=httpx.MockTransport(ahandler))


def _take(gen, n):
    out = []
    for ev in gen:
        out.append(ev)
        if len(out) == n:
            break
    gen.close()
    return out


# --- route conformance (router object, not create_app) -----------------------

def _realtime_backend_routes():
    from skeleton.api.realtime_routes import router  # mounted at /api/v1

    out = set()
    for route in router.routes:
        for method in getattr(route, "methods", None) or ():
            out.add((method, "/api/v1" + route.path))
    return out


@pytest.mark.parametrize("method,path", list(events_mod.SDK_ROUTES))
def test_realtime_sdk_routes_exist_in_backend(method, path):
    assert (method, path) in _realtime_backend_routes(), f"{method} {path} not served"


def test_realtime_route_table_is_exactly_the_three_routes():
    assert set(events_mod.SDK_ROUTES) == {
        ("GET", "/api/v1/events"), ("GET", "/api/v1/events/slo"), ("POST", "/api/v1/presence")}


# --- stream_events over SSE --------------------------------------------------

def test_stream_events_hits_canonical_stream_with_job_filter_seal_and_resume(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    seen = []

    def handler(req):
        seen.append(req)
        if len(seen) == 1:
            return _sse_response([_ev(7), ControlEvent(type="stream.reset", ts=TS, payload={"head_id": "9"}), _ev(10)])
        return _sse_response([_ev(11)])

    builds = BuildsClient(_gw(seal=RequestSealer("sdk-test")), actor_id="u", tenant_id="t")
    evs = _take(builds.stream_events("e1", last_event_id="6", http_client=_async_client(handler),
                                     realtime_options=_opts()), 4)
    assert [e.type for e in evs] == ["build.progress", "stream.reset", "build.progress", "build.progress"]
    assert [e.id for e in evs] == ["7", None, "10", "11"]
    assert evs[1].is_control and evs[1].payload == {"head_id": "9"}
    first = evs[0]
    assert first.is_envelope_v1 and first.job_id == "e1" and first.payload == {"i": 7}
    r0 = seen[0]
    assert r0.url.path == "/api/v1/events"
    assert r0.url.params["channels"] == "build,agent" and r0.url.params["job_id"] == "e1"
    assert r0.url.params["actor_id"] == "u" and r0.url.params["tenant_id"] == "t"
    assert r0.headers["last-event-id"] == "6"
    assert r0.headers["x-gf-seal"].startswith("sdk-test.")
    assert re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", r0.headers["x-request-id"])
    # reconnect resumes from the last delivered id (#4128 RealtimeClient)
    assert seen[1].headers["last-event-id"] == "10"


def test_cursor_is_a_resume_point_and_conflicts_are_rejected():
    seen = []

    def handler(req):
        seen.append(req)
        return _sse_response([_ev(5)])

    builds = BuildsClient(_gw(), actor_id="u", tenant_id="t")
    _take(builds.stream_events("e1", cursor="4", http_client=_async_client(handler), realtime_options=_opts()), 1)
    assert seen[0].headers["last-event-id"] == "4"
    with pytest.raises(ValueError):
        next(builds.stream_events("e1", last_event_id="1", cursor="2"))
    with pytest.raises(ValueError):
        builds.stream_events("")


def test_cancel_token_stops_stream():
    tok = CancelToken()

    def handler(req):
        return _sse_response([_ev(1), _ev(2), _ev(3)])

    builds = BuildsClient(_gw(), actor_id="u", tenant_id="t")
    out = []
    with pytest.raises(SkeletonCancelledError):
        for ev in builds.stream_events("e1", tok, http_client=_async_client(handler), realtime_options=_opts()):
            out.append(ev)
            tok.cancel()
    assert [e.id for e in out] == ["1"]


def test_lagged_control_surfaces_then_resumes():
    seen = []

    def handler(req):
        seen.append(req)
        if len(seen) == 1:
            return _sse_response([_ev(3), ControlEvent(type="stream.lagged", ts=TS, payload={"dropped": 2})])
        return _sse_response([_ev(4)])

    evs = _take(BuildsClient(_gw(), actor_id="u", tenant_id="t").stream_events(
        "e1", http_client=_async_client(handler), realtime_options=_opts()), 3)
    assert [e.type for e in evs] == ["build.progress", "stream.lagged", "build.progress"]
    assert seen[1].headers["last-event-id"] == "3"


def test_401_remints_seal_once_then_raises(monkeypatch):
    monkeypatch.setenv("GF_SEAL_SECRET", SECRET)
    seals = []

    def handler(req):
        seals.append(req.headers.get("x-gf-seal"))
        return httpx.Response(401, json={"error": "invalid_seal"})

    minted = []

    class _Counting(RequestSealer):
        __slots__ = ()

        def invalidate(self):
            minted.append(1)
            super().invalidate()

    sealer = _Counting("sdk-test")
    with pytest.raises(RealtimeAuthError) as ei:
        list(BuildsClient(_gw(seal=sealer), actor_id="u", tenant_id="t").stream_events(
            "e1", http_client=_async_client(handler), realtime_options=_opts()))
    assert ei.value.status_code == 401
    assert len(seals) == 2 and minted == [1]


def test_403_is_not_retried():
    hits = []

    def handler(req):
        hits.append(1)
        return httpx.Response(403, json={"detail": {"error": "channel_forbidden"}})

    with pytest.raises(RealtimeAuthError):
        list(BuildsClient(_gw(seal=None), actor_id="u", tenant_id="t").stream_events(
            "e1", http_client=_async_client(handler), realtime_options=_opts()))
    assert hits == [1]


def test_missing_local_seal_secret_raises_config_error(monkeypatch):
    monkeypatch.delenv("GF_SEAL_SECRET", raising=False)
    monkeypatch.delenv("GF_SEAL_KEYRING", raising=False)
    builds = BuildsClient(_gw(seal=RequestSealer("sdk-test")), actor_id="u", tenant_id="t")
    with pytest.raises(SkeletonSealConfigError):
        list(builds.stream_events("e1", http_client=_async_client(lambda r: _sse_response([])),
                                  realtime_options=_opts()))


# --- server-side job filter with #4128's real hub ----------------------------

def test_job_id_filter_is_server_side_inprocess_hub():
    from skeleton.client.realtime import InProcessTransport

    hub = RealtimeHub(id_seed=100, heartbeat_interval_s=0.05,
                      authorizer=lambda principal, channel: bool(principal))
    hub.publish("build", "build.started", {"n": 1}, job_id="e1", owner="ui")
    hub.publish("build", "build.started", {"n": 2}, job_id="other", owner="ui")
    hub.publish("agent", "agent.status", {"n": 3}, job_id="e1", owner="ui")
    hub.publish("build", "build.progress", {"n": 4}, job_id="e1", owner="ui")
    builds = BuildsClient(_gw(), actor_id="u", tenant_id="t")
    evs = _take(builds.stream_events("e1", last_event_id="100",
                                     transport=InProcessTransport(hub, principal="ui"),
                                     realtime_options=_opts()), 3)
    assert [(e.channel, e.payload["n"]) for e in evs] == [("build", 1), ("agent", 3), ("build", 4)]
    assert {e.job_id for e in evs} == {"e1"}


def test_build_stream_preserves_service_bearer_and_attester_with_scoped_job():
    seen = []

    def handler(req):
        seen.append(req)
        return _sse_response([_ev(8)])

    headers = BuildsClient.service_headers("test-only-token", "test-attester")
    gateway = GatewayClient(
        "http://test",
        headers=headers,
        client=httpx.Client(
            base_url="http://test",
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"slo": {}, "hub": {}})
            ),
        ),
    )
    builds = BuildsClient(gateway, actor_id="actor-1", tenant_id="tenant-2")
    _take(
        builds.stream_events(
            "e1", http_client=_async_client(handler), realtime_options=_opts()
        ),
        1,
    )
    # The pump thread may reconnect (zero-delay backoff) before the generator
    # is closed, so assert on every request rather than an exact count.
    assert seen
    for req in seen:
        assert req.headers["authorization"] == "Bearer test-only-token"
        assert req.headers["x-zaibatsu-attester"] == "test-attester"
        assert req.url.params["actor_id"] == "actor-1"
        assert req.url.params["tenant_id"] == "tenant-2"
        assert req.url.params["job_id"] == "e1"


def test_direct_job_stream_fails_closed_without_actor_and_tenant_scope():
    stream = EventsClient(_gw()).stream(job_id="exec-1")
    with pytest.raises(ValueError, match="job streams require"):
        next(stream)


def test_build_stream_uses_scoped_query_even_with_special_characters():
    seen = []

    def handler(req):
        seen.append(req)
        return _sse_response([_ev(5)])

    builds = BuildsClient(_gw(), actor_id="same&actor", tenant_id="two / tenants")
    _take(builds.stream_events("e1", http_client=_async_client(handler), realtime_options=_opts()), 1)
    assert seen[0].url.params["actor_id"] == "same&actor"
    assert seen[0].url.params["tenant_id"] == "two / tenants"
    assert seen[0].url.params["job_id"] == "e1"


# --- SLO wrapper / per-execution view kept -----------------------------------

def test_events_slo_wrapper():
    seen = []

    def handler(req):
        seen.append((req.method, req.url.path, req.headers.get("x-gf-seal")))
        return httpx.Response(200, json={"slo": {"connect_success": 1.0}, "hub": {"subscribers": 0}})

    out = EventsClient(_gw(sync_handler=handler)).slo()
    assert out["slo"]["connect_success"] == 1.0 and seen[0][:2] == ("GET", "/api/v1/events/slo")


def test_per_execution_snapshot_view_kept():
    def handler(req):
        assert req.url.path == "/api/v1/engine/executions/e1/events"
        return httpx.Response(200, json={"execution_id": "e1", "events": [{"type": "x"}], "next_sequence": 1})

    builds = BuildsClient(_gw(sync_handler=handler), actor_id="u", tenant_id="t")
    assert builds.events("e1")["next_sequence"] == 1
    assert [e.type for e in builds.stream_execution_events("e1")] == ["x"]
