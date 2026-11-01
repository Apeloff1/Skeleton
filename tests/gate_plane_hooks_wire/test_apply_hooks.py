import asyncio

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from skeleton.gate_plane import create_app_hooks as h
from skeleton.gate_plane.core_mount import DispatchScheduler, install_core_v1


class _FakeCoreModule:
    def __init__(self):
        self.router = APIRouter()

        @self.router.get("/api/v1/core/ping")
        def ping():
            return {"ok": True}

    def install_error_handler(self, app):
        app.state.core_err = True


def _core_hook(calls):
    def hook(app):
        calls.append(1)
        sched = DispatchScheduler(dispatch=lambda n: "rep", interval=0.01, jitter=0)
        app.state.test_sched = sched
        return install_core_v1(app, loader=_FakeCoreModule, scheduler=sched)
    return hook


def test_registered_hook_is_core_mount():
    assert h.resolve_create_app_hooks() == [install_core_v1]


def test_routes_mounted_and_scheduler_starts_and_stops(monkeypatch):
    monkeypatch.delenv(h.CREATE_APP_HOOKS_ENV, raising=False)
    app, calls = FastAPI(), []
    rep = h.apply_create_app_hooks(app, [_core_hook(calls)])
    assert rep["errors"] == {} and len(rep["applied"]) == 1
    assert "/api/v1/core/ping" in app.openapi()["paths"]
    sched = app.state.test_sched
    with TestClient(app) as c:
        assert sched.running
        assert c.get("/api/v1/core/ping").json() == {"ok": True}
        for _ in range(100):
            if sched.stats.ticks:
                break
            asyncio.run(asyncio.sleep(0.01))
        assert sched.stats.ticks >= 1
    assert not sched.running


def test_idempotent(monkeypatch):
    monkeypatch.delenv(h.CREATE_APP_HOOKS_ENV, raising=False)
    app, calls = FastAPI(), []
    h.apply_create_app_hooks(app, [_core_hook(calls)])
    rep = h.apply_create_app_hooks(app, [_core_hook(calls)])
    assert calls == [1] and rep.get("skipped") == "already-applied"
    assert app.state.core_v1_mounted is True
    assert list(app.openapi()["paths"]) == ["/api/v1/core/ping"]


@pytest.mark.parametrize("val", ["0", "false", "off", "NO"])
def test_env_flag_disables(monkeypatch, val):
    monkeypatch.setenv(h.CREATE_APP_HOOKS_ENV, val)
    app, calls = FastAPI(), []
    assert h.apply_create_app_hooks(app, [_core_hook(calls)])["enabled"] is False
    assert calls == []


def test_error_isolation(monkeypatch):
    monkeypatch.delenv(h.CREATE_APP_HOOKS_ENV, raising=False)
    app, calls = FastAPI(), []

    def boom(app):
        raise RuntimeError("bad hook")

    rep = h.apply_create_app_hooks(app, [boom, _core_hook(calls)])
    assert "bad hook" in next(iter(rep["errors"].values()))
    assert calls == [1] and app.state.create_app_hooks_report is rep


def test_resolve_failure_isolated(monkeypatch):
    monkeypatch.delenv(h.CREATE_APP_HOOKS_ENV, raising=False)
    monkeypatch.setattr(h, "CREATE_APP_HOOKS", ("no.such.module:x",))
    rep = h.apply_create_app_hooks(FastAPI())
    assert "<resolve>" in rep["errors"] and rep["applied"] == []


def test_server_calls_hooks_in_factory_not_lifespan():
    import pathlib
    src = pathlib.Path("skeleton/api/server.py").read_text()
    body = src[src.index("def create_app("):]
    i = body.index("apply_create_app_hooks(app)")
    assert i < body.index('@app.on_event("startup")')


@pytest.mark.parametrize(
    ("checker", "allowed"),
    [
        (h.assert_open_probe_health, "/health"),
        (h.assert_open_probe_ready, "/ready"),
        (h.assert_open_probe_api_v1_health, "/api/v1/health"),
        (h.assert_open_probe_api_v1_health_live, "/api/v1/health/live"),
        (h.assert_open_probe_api_v1_health_ready, "/api/v1/health/ready"),
        (h.assert_open_probe_metrics, "/metrics"),
        (h.assert_open_probe_api_v1_metrics, "/api/v1/metrics"),
        (h.assert_open_probe_root, "/"),
        (h.assert_open_probe_cortex_status, "/cortex/status"),
        (h.assert_open_probe_cockpit, "/cockpit"),
        (h.assert_open_probe_docs, "/docs"),
        (h.assert_open_probe_openapi_json, "/openapi.json"),
        (h.assert_open_probe_redoc, "/redoc"),
    ],
)
def test_public_probe_path_requires_complete_component(checker, allowed):
    assert checker(allowed)["ok"] is True
    assert checker(allowed + "private")["ok"] is False
    assert checker(allowed + "-admin")["ok"] is False
    if allowed != "/":
        assert checker(allowed + "/live")["ok"] is True
    else:
        assert checker("/admin")["ok"] is False
