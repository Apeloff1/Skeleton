"""Server-side route conformance for the realtime transport (ADR #4101)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")

from starlette.requests import Request  # noqa: E402

from skeleton.api.middleware import GatePolicy  # noqa: E402
from skeleton.api.realtime_routes import execution_stream_or_none, router  # noqa: E402
from skeleton.realtime import RealtimeHub  # noqa: E402


def test_router_exposes_canonical_paths_and_methods():
    routes = {(r.path, tuple(sorted(r.methods))) for r in router.routes}
    assert ("/events", ("GET",)) in routes
    assert ("/presence", ("POST",)) in routes
    assert ("/presence", ("GET",)) in routes
    assert ("/events/slo", ("GET",)) in routes


def test_realtime_prefixes_are_written_gate_domains_not_open_routes():
    policy = GatePolicy()
    for path in ("/api/v1/events", "/api/v1/presence", "/api/v1/events/slo"):
        assert policy.required_domain(path) == "realtime"
        assert not policy.is_open_route(path)
    assert policy.required_domain("/api/v1/eventsx") is None


def test_create_app_mounts_realtime_routes_and_hub():
    """Must not skip (Jenkins S2-7). FastAPI >= 0.142 includes routers lazily
    (``_IncludedRouter`` entries with ``path=None``), so walk the composed
    route table with the cortex mount guard's ``iter_route_paths``."""
    from skeleton.api.cortex_mount_guard import iter_route_paths
    from skeleton.api.server import create_app

    app = create_app()
    paths = set(iter_route_paths(app))
    assert {"/api/v1/events", "/api/v1/presence", "/api/v1/events/slo"} <= paths
    assert "/api/v1/engine/executions/{execution_id}/events" in paths
    assert isinstance(app.state.realtime_hub, RealtimeHub)


def _request(app, accept):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/engine/executions/exec-1/events",
        "headers": [(b"accept", accept.encode())],
        "query_string": b"",
        "app": app,
    }
    return Request(scope)


def test_engine_events_route_keeps_json_unless_sse_requested():
    app = fastapi.FastAPI()
    app.state.realtime_hub = RealtimeHub(id_seed=1, authorizer=lambda p, c: bool(p))
    assert execution_stream_or_none(_request(app, "application/json"), "exec-1", principal="svc") is None
    bare = fastapi.FastAPI()
    assert execution_stream_or_none(_request(bare, "text/event-stream"), "exec-1", principal="svc") is None
    stream = execution_stream_or_none(_request(app, "text/event-stream"), "exec-1", principal="svc")
    assert stream is not None and stream.media_type == "text/event-stream"
    (sub,) = app.state.realtime_hub._subs.values()
    assert sub.job_id == "exec-1" and sub.channels == ("build", "agent")
    assert sub.job_grant == "exec-1"
