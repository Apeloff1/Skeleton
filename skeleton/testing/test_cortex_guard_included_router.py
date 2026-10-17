"""Cortex guard must see through FastAPI's lazy included routers (fail-closed)."""
import pytest
from fastapi import APIRouter, FastAPI
from starlette.applications import Starlette
from starlette.routing import Mount, Route, WebSocketRoute

from skeleton.api.cortex_mount_guard import (
    CortexRouteGuardMiddleware,
    iter_route_paths,
    reject_cortex_secret_routes,
)

SECRETS = "cortex secrets"


def _ep(request):  # pragma: no cover
    return None


def _secrets_router():
    inner = APIRouter(prefix="/secrets")

    @inner.get("/{name}")
    def read(name: str):  # pragma: no cover
        return {}

    return inner


def test_secrets_route_inside_included_router_is_rejected():
    outer = APIRouter()
    outer.include_router(_secrets_router())
    app = FastAPI()
    app.include_router(outer, prefix="/api/v1")
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(app)


def test_deep_nesting_composes_prefixes():
    leaf = APIRouter()

    @leaf.get("/{name}")
    def read(name: str):  # pragma: no cover
        return {}

    r3 = APIRouter()
    r3.include_router(leaf, prefix="/secrets")
    r2 = APIRouter()
    r2.include_router(r3, prefix="/v1")
    r1 = APIRouter()
    r1.include_router(r2, prefix="/api")
    app = FastAPI()
    app.include_router(r1)
    assert "/api/v1/secrets/{name}" in iter_route_paths(app)
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(app)


def test_same_router_at_two_prefixes_is_walked_twice():
    shared = _secrets_router()
    app = FastAPI()
    app.include_router(shared, prefix="/harmless")
    app.include_router(shared, prefix="/api/v1")
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(app)


def test_mount_and_sub_app_are_walked():
    sub = Starlette(routes=[Route("/secrets/{name}", _ep)])
    app = FastAPI()
    app.mount("/api/v1", sub)
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(app)
    app2 = Starlette(routes=[Mount("/api", routes=[Mount("/v1", routes=[Route("/secrets", _ep)])])])
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(app2)


def test_opaque_mount_fails_closed_only_where_secrets_reachable():
    async def opaque(scope, receive, send):  # pragma: no cover
        return None

    ok = Starlette(routes=[Mount("/static", app=opaque)])
    reject_cortex_secret_routes(ok)
    for prefix in ("/", "/api", "/api/v1", "/api/v1/secrets"):
        bad = Starlette(routes=[Mount(prefix, app=opaque)])
        with pytest.raises(RuntimeError):
            reject_cortex_secret_routes(bad)


def test_websocket_route_is_checked():
    async def ws(websocket):  # pragma: no cover
        return None

    app = Starlette(routes=[Mount("/api/v1", routes=[WebSocketRoute("/secrets/stream", ws)])])
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(app)
    fa = FastAPI()
    r = APIRouter()

    @r.websocket("/secrets/live")
    async def live(websocket):  # pragma: no cover
        return None

    fa.include_router(r, prefix="/api/v1")
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(fa)


def test_encoded_and_doubled_separators_are_caught():
    app = Starlette(routes=[Route("/api//v1/%2573ecrets/x", _ep)])
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(app)


def test_benign_included_router_passes_and_opaque_entry_fails():
    r = APIRouter(prefix="/projects")

    @r.get("")
    def lst():  # pragma: no cover
        return {}

    app = FastAPI()
    app.include_router(r, prefix="/api/v1")
    reject_cortex_secret_routes(app)
    assert "/api/v1/projects" in iter_route_paths(app)

    class Opaque:
        pass

    class FakeApp:
        routes = [Opaque()]

    with pytest.raises(RuntimeError, match="uninspectable"):
        reject_cortex_secret_routes(FakeApp())

    class NoRoutes:
        pass

    with pytest.raises(RuntimeError, match="inventory unavailable"):
        reject_cortex_secret_routes(NoRoutes())


def test_late_added_route_is_caught_by_middleware_hook():
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/ok")
    def ok():
        return {"ok": True}

    app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)
    client = TestClient(app)
    assert client.get("/ok").status_code == 200
    app.include_router(_secrets_router(), prefix="/api/v1")  # added after creation
    r = client.get("/ok")
    assert r.status_code == 503 and r.json() == {"error": "route_guard_violation"}


def test_host_routes_are_walked_and_opaque_host_fails():
    from starlette.routing import Host, Router

    app = Starlette(routes=[Host("api.example.com", app=Router(routes=[Route("/api/v1/secrets", _ep)]))])
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(app)

    async def opaque(scope, receive, send):  # pragma: no cover
        return None

    with pytest.raises(RuntimeError, match="uninspectable"):
        reject_cortex_secret_routes(Starlette(routes=[Host("x.example.com", app=opaque)]))
