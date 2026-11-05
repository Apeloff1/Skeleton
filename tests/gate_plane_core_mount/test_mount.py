import contextlib
import types

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from skeleton.api.v1_edge.registry import RouteRegistry
from skeleton.gate_plane import create_app_hooks
from skeleton.gate_plane.core_mount import (
    DispatchScheduler,
    core_v1_route_specs,
    install_core_v1,
    register_core_v1_routes,
)


def fake_loader():
    router = APIRouter(prefix="/api/v1/core")

    @router.get("/webhooks")
    def lst():
        return {"items": [], "next_cursor": None, "has_more": False}

    mod = types.SimpleNamespace(router=router, handlers=[])
    mod.install_error_handler = lambda app: mod.handlers.append(app)
    return mod


def test_specs_cover_contract_table():
    specs = core_v1_route_specs()
    assert len(specs) == 10
    assert all(s.full_path.startswith("/api/v1/core/") for s in specs)
    idem = {(s.method, s.path) for s in specs if s.idempotent_writes}
    assert idem == {("POST", "/core/webhooks"), ("POST", "/core/deliveries/{delivery_id}/replay")}
    assert all("core:write" in s.scopes for s in specs if s.method != "GET")


def test_register_is_idempotent_and_matches():
    reg = RouteRegistry()
    assert register_core_v1_routes(reg) == 10
    assert register_core_v1_routes(reg) == 0
    spec, params, _ = reg.match("PATCH", "/api/v1/core/webhooks/wh_1")
    assert spec.quota_class == "core_write" and params == {"webhook_id": "wh_1"}


def test_install_mounts_once_and_runs_scheduler_in_lifespan():
    calls = []
    started = []

    @contextlib.asynccontextmanager
    async def original(app):
        started.append("orig-up")
        yield
        started.append("orig-down")

    app = FastAPI(lifespan=original)
    reg = RouteRegistry()
    sched = DispatchScheduler(dispatch=calls.append, interval=0.01, jitter=0)
    out = install_core_v1(app, registry=reg, scheduler=sched, loader=fake_loader)
    assert out == {"edge_routes_added": 10, "mounted": True, "scheduled": True}
    again = install_core_v1(app, registry=reg, loader=fake_loader)
    assert again["mounted"] is False and again["scheduled"] is False

    with TestClient(app) as c:
        assert c.get("/api/v1/core/webhooks").json()["has_more"] is False
        assert sched.running
    assert not sched.running
    assert started == ["orig-up", "orig-down"]
    assert calls and set(calls) == {50}


def test_hook_registered_in_create_app_hooks():
    hooks = create_app_hooks.resolve_create_app_hooks()
    assert install_core_v1 in hooks
