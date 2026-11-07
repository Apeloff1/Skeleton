"""Negative tests for the TD security review of #4129 (one or more per blocker)."""
from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import BaseRoute, Match, Mount, Route, Router

from skeleton.api.cortex_mount_guard import (
    CortexRouteGuardMiddleware,
    iter_route_paths,
    reject_cortex_secret_routes,
)

SECRETS = "cortex secrets"
CORTEX = "unchartered cortex HTTP route"
UNINSPECTABLE = "uninspectable"
DOT = "dot segment"


def _ep(request):  # pragma: no cover
    return None


async def _opaque(scope, receive, send):  # pragma: no cover
    return None


class _Deck:
    """Stand-in deck: cortex handlers only touch it at request time."""


def _cortex_router() -> APIRouter:
    from skeleton.api.cortex_routes import register_routes

    router = APIRouter()
    register_routes(router, _Deck())
    return router


# -- Blocker 1: known route types only -------------------------------------

def test_unknown_route_class_with_str_path_refuses():
    class Custom(BaseRoute):
        path = "/api/v1/health"

        def matches(self, scope):  # pragma: no cover
            return Match.FULL, {}

    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(Starlette(routes=[Custom()]))


def test_route_subclass_overriding_matches_refuses():
    class Sneaky(Route):
        def matches(self, scope):  # pragma: no cover
            return Match.FULL, {}

    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(Starlette(routes=[Sneaky("/ok", _ep)]))


def test_included_router_with_non_str_prefix_refuses():
    r = APIRouter()

    @r.get("/x")
    def x():  # pragma: no cover
        return {}

    app = FastAPI()
    app.include_router(r, prefix="/a")
    included = app.router.routes[-1]
    if not hasattr(included, "include_context"):
        pytest.skip("FastAPI without lazy _IncludedRouter")
    included.include_context.prefix = None
    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(app)


def test_depth_over_limit_refuses():
    routes = [Route("/leaf", _ep)]
    for _ in range(40):
        routes = [Mount("/n", routes=routes)]
    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(Starlette(routes=routes))


# -- Blocker 2: opaque mount at a path-parameter prefix ---------------------

@pytest.mark.parametrize("prefix", ["/{tenant}", "/api/{v}", "/{a}/{b}", "/x/{p:path}"])
def test_opaque_mount_at_param_prefix_refuses(prefix):
    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(Starlette(routes=[Mount(prefix, app=_opaque)]))


def test_static_files_at_param_prefix_refuses():
    from starlette.staticfiles import StaticFiles

    static = StaticFiles(directory=".", check_dir=False)
    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(Starlette(routes=[Mount("/{tenant}", app=static)]))


# -- Blocker 3: cortex by handler identity at any prefix ---------------------

@pytest.mark.parametrize("prefix", ["", "/internal", "/x/y", "/api/v2"])
def test_cortex_router_relocated_anywhere_refuses(prefix):
    app = FastAPI()
    app.include_router(_cortex_router(), prefix=prefix)
    with pytest.raises(RuntimeError, match=CORTEX):
        reject_cortex_secret_routes(app)


def test_cortex_registered_on_mounted_sub_app_refuses():
    from skeleton.api.cortex_routes import register_routes

    sub = FastAPI()
    register_routes(sub, _Deck())
    app = Starlette(routes=[Mount("/x", app=sub)])
    with pytest.raises(RuntimeError, match=CORTEX):
        reject_cortex_secret_routes(app)


def test_every_cortex_endpoint_is_refused_individually():
    router = _cortex_router()
    assert len(router.routes) >= 40  # the ~52 unchartered endpoints
    for route in router.routes:
        app = FastAPI()
        app.router.routes.append(route)
        with pytest.raises(RuntimeError, match=CORTEX):
            reject_cortex_secret_routes(app)


def test_ai_runtime_cortex_mirror_is_refused_too():
    from skeleton.ai.runtime.api.cortex_routes import register_routes

    app = FastAPI()
    register_routes(app, _Deck())
    with pytest.raises(RuntimeError, match=CORTEX):
        reject_cortex_secret_routes(app)


def test_relocated_secrets_path_refuses_without_cortex_handler():
    app = Starlette(routes=[Route("/internal/api/v1/secrets/{name}", _ep)])
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(app)
    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(Starlette(routes=[Mount("/x/api/v1/secrets", app=_opaque)]))


# -- Blocker 4: dot segments, %2e and Unicode aliases -----------------------

@pytest.mark.parametrize("path", [
    "/api/v1/./secrets",
    "/api/v1/x/../secrets",
    "/api/v1/%2e/secrets",
    "/api/v1/%2E%2E/v1/secrets",
    "/api/v1/%252e/secrets",
])
def test_dot_segments_refuse(path):
    with pytest.raises(RuntimeError, match=DOT):
        reject_cortex_secret_routes(Starlette(routes=[Route(path, _ep)]))


@pytest.mark.parametrize("path", [
    "/api/v1/\uff53\uff45\uff43\uff52\uff45\uff54\uff53",  # fullwidth "secrets"
    "/\uff41\uff50\uff49/v1/secrets/{name}",
    "/api/v1/SECRET\u017f",  # long s casefolds to s
    "/api/v1/%EF%BD%93ecrets",  # percent-encoded fullwidth s
])
def test_unicode_aliases_refuse(path):
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(Starlette(routes=[Route(path, _ep)]))


def test_dot_segment_in_mount_prefix_refuses():
    app = Starlette(routes=[Mount("/api/./v1", routes=[Route("/ok", _ep)])])
    with pytest.raises(RuntimeError, match=DOT):
        reject_cortex_secret_routes(app)


# -- Blocker 5: default re-check, nested late additions, any exception -------

def test_nested_late_addition_is_caught():
    inner = APIRouter()

    @inner.get("/ok")
    def ok():
        return {"ok": True}

    outer = APIRouter()
    outer.include_router(inner, prefix="/v1")
    app = FastAPI()
    app.include_router(outer, prefix="/api")
    app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)
    client = TestClient(app)
    assert client.get("/api/v1/ok").status_code == 200

    @inner.get("/secrets/{name}")
    def late(name: str):  # pragma: no cover
        return {}

    if "/api/v1/secrets/{name}" not in iter_route_paths(app):
        pytest.skip("FastAPI without live included routers")
    assert client.get("/api/v1/ok").status_code == 503


def test_same_length_swap_is_caught():
    app = Starlette(routes=[Mount("/api/v1", routes=[Route("/ok", _ep)])])
    app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)
    client = TestClient(app)
    client.get("/nope")
    app.router.routes[0].routes[0] = Route("/secrets", _ep)
    assert client.get("/nope").status_code == 503


def test_any_exception_during_check_is_a_violation(monkeypatch):
    import skeleton.api.cortex_mount_guard as guard

    app = Starlette(routes=[Route("/ok", lambda r: None)])
    app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)

    def boom(_app):
        raise ValueError("unexpected")

    monkeypatch.setattr(guard, "reject_cortex_secret_routes", boom)
    assert TestClient(app).get("/ok").status_code == 503


def test_lifespan_startup_fails_on_violation():
    app = FastAPI()
    app.add_middleware(CortexRouteGuardMiddleware, guarded_app=app)
    app.include_router(_cortex_router(), prefix="/hidden")
    with pytest.raises(Exception):
        with TestClient(app):
            pass


def test_create_app_installs_guard_by_default_and_catches_late_cortex():
    from skeleton.api.server import create_app

    app = create_app()
    assert any(m.cls is CortexRouteGuardMiddleware for m in app.user_middleware)
    client = TestClient(app)
    before = client.get("/cortex/status").status_code
    assert before != 503
    app.include_router(_cortex_router(), prefix="/late")
    assert client.get("/cortex/status").status_code == 503


def test_ai_runtime_create_app_installs_guard_by_default():
    from skeleton.ai.runtime.api.server import create_app

    app = create_app()
    assert any(m.cls is CortexRouteGuardMiddleware for m in app.user_middleware)


# -- Blocker 6: _low_priority_routes / frontend() ---------------------------

def test_low_priority_opaque_entry_refuses():
    app = FastAPI()
    app.router._low_priority_routes = [Mount("/", app=_opaque)]
    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(app)


def test_low_priority_unknown_entry_refuses():
    app = FastAPI()
    app.router._low_priority_routes = [object()]
    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(app)


def test_low_priority_secrets_route_in_included_router_refuses():
    r = APIRouter()
    r._low_priority_routes = [Route("/secrets/{name}", _ep)]
    app = FastAPI()
    app.include_router(r, prefix="/api/v1")
    with pytest.raises(RuntimeError, match=SECRETS):
        reject_cortex_secret_routes(app)


def test_frontend_at_root_refuses(tmp_path):
    app = FastAPI()
    if not hasattr(app, "frontend") and not hasattr(app.router, "frontend"):
        pytest.skip("FastAPI without frontend()")
    target = app if hasattr(app, "frontend") else app.router
    target.frontend("/", directory=str(tmp_path))
    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(app)


# -- Blocker 7: cycles ------------------------------------------------------

def test_mount_cycle_refuses():
    mount = Mount("/loop", routes=[])
    mount.routes.append(mount)
    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(Starlette(routes=[mount]))


def test_router_cycle_via_sub_app_refuses():
    inner = Router(routes=[])
    inner.routes.append(Mount("/again", app=inner))
    with pytest.raises(RuntimeError, match=UNINSPECTABLE):
        reject_cortex_secret_routes(Starlette(routes=[Mount("/a", app=inner)]))


def test_same_router_twice_is_not_a_cycle():
    shared = APIRouter()

    @shared.get("/ok")
    def ok():  # pragma: no cover
        return {}

    app = FastAPI()
    app.include_router(shared, prefix="/a")
    app.include_router(shared, prefix="/b")
    assert {"/a/ok", "/b/ok"} <= set(iter_route_paths(app))
