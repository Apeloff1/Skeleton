"""Extra negative tests for the fail-closed cortex guard (Jenkins #4129 review gaps)."""
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Host, Mount, Route, Router

from skeleton.api.cortex_mount_guard import (
    CortexRouteGuardMiddleware,
    iter_route_paths,
    reject_cortex_secret_routes,
)


def _ep(request):  # pragma: no cover
    return None


def test_every_cortex_endpoint_refused_by_module_not_just_secrets():
    from skeleton.api import cortex_routes

    probe = APIRouter()
    cortex_routes.register_routes(probe, MagicMock())
    paths = [r.path for r in probe.routes]
    assert len(paths) >= 40  # the ~52 unchartered endpoints
    for route in probe.routes:  # each one alone, at a relocated prefix
        one = APIRouter()
        one.routes.append(route)
        app = FastAPI()
        app.include_router(one, prefix="/x/y")
        with pytest.raises(RuntimeError, match="cortex"):
            reject_cortex_secret_routes(app)


def test_ai_runtime_cortex_module_also_refused():
    from skeleton.ai.runtime.api import cortex_routes as rt

    probe = APIRouter()
    rt.register_routes(probe, MagicMock())
    app = FastAPI()
    app.include_router(probe, prefix="/internal")
    with pytest.raises(RuntimeError, match="cortex"):
        reject_cortex_secret_routes(app)


@pytest.mark.parametrize("path", ["/internal/api/v1/secrets/k", "/x/API/v1/%73ecrets",
                                  "/api/v1/%252e/secrets", "/api/v1/\uff0e\uff0e/secrets"])
def test_relocated_and_aliased_secret_paths_refused(path):
    with pytest.raises(RuntimeError):
        reject_cortex_secret_routes(Starlette(routes=[Route(path, _ep)]))


def test_depth_over_limit_raises():
    inner = Mount("/l", routes=[Route("/ok", _ep)])
    for _ in range(40):
        inner = Mount("/l", routes=[inner])
    with pytest.raises(RuntimeError, match="uninspectable"):
        reject_cortex_secret_routes(Starlette(routes=[inner]))


def test_host_cycle_raises():
    r = Router(routes=[])
    r.routes.append(Host("a.example.com", app=r))
    with pytest.raises(RuntimeError, match="cycle"):
        reject_cortex_secret_routes(Starlette(routes=[Host("b.example.com", app=r)]))


def test_unknown_route_subclass_like_object_refused():
    class Lookalike:
        path = "/api/v1/health"
        endpoint = staticmethod(_ep)
        app = None

    app = FastAPI()
    app.router.routes.append(Lookalike())
    with pytest.raises(RuntimeError, match="unknown route type"):
        reject_cortex_secret_routes(app)


def test_nested_late_addition_to_included_router_is_refused_per_request():
    app = FastAPI()
    sub = APIRouter()

    @sub.get("/ok")
    def ok():
        return {"ok": True}

    app.include_router(sub, prefix="/api/v1")
    app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)
    client = TestClient(app)
    assert client.get("/api/v1/ok").status_code == 200
    sub.add_api_route("/secrets/late", lambda: {})  # noqa: PIE807  # nested, top-level len unchanged
    r = client.get("/api/v1/ok")
    assert r.status_code == 503 and r.json() == {"error": "route_guard_violation"}


def test_any_walk_exception_is_a_violation():
    app = FastAPI()

    @app.get("/ok")
    def ok():
        return {}

    app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)
    client = TestClient(app)
    app.router.routes.append(object())
    assert client.get("/ok").status_code == 503


def test_create_app_installs_guard_middleware_by_default_and_boots():
    from skeleton.api.server import create_app

    app = create_app()
    assert any(m.cls is CortexRouteGuardMiddleware for m in app.user_middleware)
    assert "/api/v1/projects" in iter_route_paths(app)
    assert "/api/v1/events" in iter_route_paths(app)
