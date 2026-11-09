"""Cortex HTTP secrets must remain unmounted and fail closed."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from skeleton.api.cortex_mount_guard import reject_cortex_secret_routes


def _ep(request):  # pragma: no cover
    return None


def _app(*routes):
    # Real Starlette route objects only: duck-typed fixtures are refused (B1).
    return Starlette(routes=list(routes))


@pytest.mark.parametrize("path", [
    "/api/v1/secrets",
    "/api/v1/secrets/{name}",
    "/api/v1/secrets/{name}/rotate",
    "/api/v1/%73ecrets/{name}",
    "/API/V1/SECRETS/{name}",
    "/api/v1//secrets/{name}",
    "/api/v1///secrets/{name}",
    "/api/v1/%2573ecrets/{name}",
])
def test_unchartered_secret_routes_are_rejected(path: str) -> None:
    app = _app(Route(path, _ep))
    with pytest.raises(RuntimeError, match="cortex secrets"):
        reject_cortex_secret_routes(app)


@pytest.mark.parametrize("path", [
    "/api/v1/health",
    "/api/v1/commands/contracts",
    "/api/v1/swarm/status",
    "/cortex/status",
    "/api/v1/secrets-metadata",
])
def test_unrelated_registered_http_routes_still_work(path: str) -> None:
    reject_cortex_secret_routes(_app(Route(path, _ep)))


def test_included_routers_without_their_own_path_are_inspected() -> None:
    ok = APIRouter()
    ok.add_api_route("/health", lambda: {})  # noqa: PIE807
    app = FastAPI()
    app.include_router(ok, prefix="/api/v1")
    reject_cortex_secret_routes(app)
    bad = APIRouter()
    bad.add_api_route("/secrets/{name}", lambda name: {})
    app.include_router(bad, prefix="/api/v1")
    with pytest.raises(RuntimeError, match="cortex secrets"):
        reject_cortex_secret_routes(app)


def test_duck_typed_route_objects_are_refused() -> None:
    # B1: a str .path no longer makes an object trusted; non-allowlisted fails closed.
    for fake in (SimpleNamespace(path="/api/v1/health"), SimpleNamespace(path=None),
                 SimpleNamespace(path=None, effective_candidates=lambda: [])):
        with pytest.raises(RuntimeError, match="uninspectable"):
            reject_cortex_secret_routes(SimpleNamespace(routes=[fake]))


def test_mounted_child_paths_are_joined_before_the_secrets_check() -> None:
    app = _app(Mount("/api/v1", routes=[Route("/secrets/rotate", _ep)]))
    with pytest.raises(RuntimeError, match="cortex secrets"):
        reject_cortex_secret_routes(app)


def test_route_inventory_is_required() -> None:
    with pytest.raises(RuntimeError, match="route inventory"):
        reject_cortex_secret_routes(SimpleNamespace())


def test_lazy_included_router_prefixes_cannot_hide_nested_secret_paths() -> None:
    leaf = APIRouter()
    leaf.add_api_route("/secrets/rotate", lambda: {})  # noqa: PIE807
    mid = APIRouter()
    mid.include_router(leaf, prefix="/v1")
    app = FastAPI()
    app.include_router(mid, prefix="/api")
    with pytest.raises(RuntimeError, match="cortex secrets"):
        reject_cortex_secret_routes(app)


def test_opaque_mount_cannot_mask_secret_prefix() -> None:
    # B2: an ASGI app without a route table is refused at every prefix.
    async def opaque(scope, receive, send):  # pragma: no cover
        return None

    for path in ("/", "/api", "/api/v1", "/api/v1/secrets", "/public", "/{tenant}"):
        with pytest.raises(RuntimeError, match="uninspectable"):
            reject_cortex_secret_routes(_app(Mount(path, app=opaque)))


def test_real_application_factory_rejects_unchartered_cortex_paths() -> None:
    from skeleton.api.server import create_app

    app = create_app()
    reject_cortex_secret_routes(app)
    paths = [getattr(route, "path", "") for route in app.routes]
    assert not any(
        path == "/api/v1/secrets" or path.startswith("/api/v1/secrets/")
        for path in paths
    )
