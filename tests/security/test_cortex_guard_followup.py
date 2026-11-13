"""Negative tests for Jenkins's #4256 review (partial, path/regex drift, StaticFiles, fingerprint)."""
import functools
import time
import warnings
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

from skeleton.api.cortex_mount_guard import (
    CortexRouteGuardMiddleware,
    reject_cortex_secret_routes,
    route_table_fingerprint,
)


def _cortex_endpoint():
    from skeleton.api import cortex_routes

    probe = APIRouter()
    cortex_routes.register_routes(probe, MagicMock())
    return probe.routes[0].endpoint


@pytest.mark.parametrize("depth", [1, 3])
def test_partial_of_cortex_handler_refused_at_any_path(depth):
    endpoint = _cortex_endpoint()
    for _ in range(depth):
        endpoint = functools.partial(endpoint)
    app = FastAPI()
    app.add_api_route("/totally/harmless", endpoint)
    with pytest.raises(RuntimeError, match="cortex"):
        reject_cortex_secret_routes(app)


def test_partial_under_wrapped_chain_refused():
    inner = functools.partial(_cortex_endpoint())

    def outer(*a, **k):  # pragma: no cover
        return inner(*a, **k)

    outer.__wrapped__ = inner
    app = FastAPI()
    app.add_api_route("/x", outer)
    with pytest.raises(RuntimeError, match="cortex"):
        reject_cortex_secret_routes(app)


class _SneakyRoute(APIRoute):
    pass


def test_path_reassigned_after_construction_refused():
    app = FastAPI()
    route = _SneakyRoute("/api/v1/secrets/{key}", lambda key: key)
    route.path = "/harmless/{key}"
    app.router.routes.append(route)
    with pytest.raises(RuntimeError, match="path_regex disagree"):
        reject_cortex_secret_routes(app)


def test_path_format_drift_refused():
    app = FastAPI()
    app.add_api_route("/ok", lambda: {})  # noqa: PIE807
    app.router.routes[-1].path_format = "/api/v1/secrets"
    with pytest.raises(RuntimeError, match="path_regex disagree"):
        reject_cortex_secret_routes(app)


def test_mount_path_reassigned_refused():
    app = FastAPI()
    app.mount("/api/v1/secrets", FastAPI())
    app.router.routes[-1].path = "/fine"
    with pytest.raises(RuntimeError, match="path_regex disagree"):
        reject_cortex_secret_routes(app)


@pytest.mark.parametrize("prefix", ["/", "/api", "/api/v1", "/API/v1", "/api/v1/secrets", "/x/api/v1/secrets"])
def test_static_files_at_or_above_protected_prefix_refused(tmp_path, prefix):
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "k").write_text("leak")
    app = FastAPI()
    app.mount(prefix, StaticFiles(directory=tmp_path))
    with pytest.raises(RuntimeError, match="StaticFiles|secrets"):
        reject_cortex_secret_routes(app)


def test_static_files_at_unrelated_prefix_still_allowed(tmp_path):
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=tmp_path))
    app.mount("/api/v2/assets", StaticFiles(directory=tmp_path))
    reject_cortex_secret_routes(app)


def _guarded():
    app = FastAPI()
    sub = APIRouter()

    @sub.get("/ok")
    def ok():
        return {"ok": True}

    app.include_router(sub, prefix="/api/v1")
    app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)
    return app, sub


def test_fingerprint_skips_full_walk_when_unchanged(monkeypatch):
    from skeleton.api import cortex_mount_guard as guard

    app, _ = _guarded()
    client = TestClient(app)
    assert client.get("/api/v1/ok").status_code == 200
    calls = []
    real = guard.reject_cortex_secret_routes
    monkeypatch.setattr(guard, "reject_cortex_secret_routes", lambda a: calls.append(1) or real(a))
    for _ in range(5):
        assert client.get("/api/v1/ok").status_code == 200
    assert calls == []


@pytest.mark.parametrize("mutation", ["nested_append", "path_reassign", "endpoint_swap"])
def test_fingerprint_change_reruns_walk_and_refuses(mutation):
    app, sub = _guarded()
    client = TestClient(app)
    assert client.get("/api/v1/ok").status_code == 200
    if mutation == "nested_append":
        sub.add_api_route("/secrets/late", lambda: {})  # noqa: PIE807
    elif mutation == "path_reassign":
        sub.routes[0].path = "/secrets/{k}"
    else:
        sub.routes[0].endpoint = functools.partial(_cortex_endpoint())
    r = client.get("/api/v1/ok")
    assert r.status_code == 503 and r.json() == {"error": "route_guard_violation"}


def test_fingerprint_changes_on_mutation():
    app, sub = _guarded()
    before = route_table_fingerprint(app)
    assert before is not None and before == route_table_fingerprint(app)
    sub.add_api_route("/other", lambda: {})  # noqa: PIE807
    assert route_table_fingerprint(app) != before


def test_per_request_cost_on_create_app_is_small():
    from skeleton.api.server import create_app

    app = create_app()
    mw = CortexRouteGuardMiddleware(None, guarded_app=app)
    assert mw._violation(force=True) is None
    n = 200
    start = time.perf_counter()
    for _ in range(n):
        assert mw._violation() is None
    per_request_ms = (time.perf_counter() - start) * 1000 / n
    assert per_request_ms < 5.0, per_request_ms


def _edge_world():
    from skeleton.testing.test_gate_plane_pack_f_agent_edge_gateway import World

    return World()


def test_mounted_standalone_agent_gateway_app_passes_and_is_walked():
    from skeleton.gate_plane.agent_edge import create_agent_gateway_app

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        edge = create_agent_gateway_app(_edge_world().gateway)
    app = FastAPI()
    app.mount("/edge", edge)
    reject_cortex_secret_routes(app)
    from skeleton.api.cortex_mount_guard import iter_route_paths

    assert any(p.startswith("/edge/") for p in iter_route_paths(app))


def test_mounted_agent_gateway_app_with_smuggled_secret_route_refused():
    from skeleton.gate_plane.agent_edge import create_agent_gateway_app

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        edge = create_agent_gateway_app(_edge_world().gateway)
    edge.add_api_route("/api/v1/secrets/k", lambda: {})  # noqa: PIE807
    app = FastAPI()
    app.mount("/edge", edge)
    with pytest.raises(RuntimeError, match="secrets"):
        reject_cortex_secret_routes(app)


def test_residual_risk_unwrapped_foreign_wrapper_is_not_detected_by_module():
    """Documented residual risk: no functools.wraps + foreign module hides identity."""
    target = _cortex_endpoint()
    ns: dict = {"target": target}
    exec("def shim(*a, **k):\n    return target(*a, **k)\n", ns)  # noqa: S102
    shim = ns["shim"]
    shim.__module__ = "some.other.module"
    app = FastAPI()
    app.add_api_route("/x", shim)
    reject_cortex_secret_routes(app)  # not detected: path checks are the only defence
