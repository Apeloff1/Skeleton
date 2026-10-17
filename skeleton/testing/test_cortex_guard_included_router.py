"""Cortex guard must see through FastAPI's lazy included routers (fail-closed)."""
import pytest
from fastapi import APIRouter, FastAPI

from skeleton.api.cortex_mount_guard import reject_cortex_secret_routes


def test_secrets_route_inside_included_router_is_rejected():
    inner = APIRouter(prefix="/secrets")

    @inner.get("/{name}")
    def read(name: str):  # pragma: no cover
        return {}

    outer = APIRouter()
    outer.include_router(inner)
    app = FastAPI()
    app.include_router(outer, prefix="/api/v1")
    with pytest.raises(RuntimeError, match="cortex secrets"):
        reject_cortex_secret_routes(app)


def test_benign_included_router_passes_and_opaque_entry_fails():
    r = APIRouter(prefix="/projects")

    @r.get("")
    def lst():  # pragma: no cover
        return {}

    app = FastAPI()
    app.include_router(r, prefix="/api/v1")
    reject_cortex_secret_routes(app)

    class Opaque:
        pass

    class FakeApp:
        routes = [Opaque()]

    with pytest.raises(RuntimeError, match="uninspectable"):
        reject_cortex_secret_routes(FakeApp())
