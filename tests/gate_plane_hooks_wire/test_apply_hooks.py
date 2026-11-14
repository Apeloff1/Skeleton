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


def _enable(monkeypatch, strict=None):
    monkeypatch.setenv(h.CREATE_APP_HOOKS_ENV, "1")
    if strict is None:
        monkeypatch.delenv(h.CREATE_APP_HOOKS_STRICT_ENV, raising=False)
    else:
        monkeypatch.setenv(h.CREATE_APP_HOOKS_STRICT_ENV, strict)


def test_routes_mounted_and_scheduler_starts_and_stops(monkeypatch):
    _enable(monkeypatch)
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
    _enable(monkeypatch)
    app, calls = FastAPI(), []
    h.apply_create_app_hooks(app, [_core_hook(calls)])
    rep = h.apply_create_app_hooks(app, [_core_hook(calls)])
    assert calls == [1] and rep.get("skipped") == "already-applied"
    assert app.state.core_v1_mounted is True
    assert list(app.openapi()["paths"]) == ["/api/v1/core/ping"]


@pytest.mark.parametrize("val", [None, "", "0", "false", "off", "NO", "maybe"])
def test_hooks_are_off_unless_env_set(monkeypatch, val):
    monkeypatch.delenv(h.CREATE_APP_HOOKS_STRICT_ENV, raising=False)
    if val is None:
        monkeypatch.delenv(h.CREATE_APP_HOOKS_ENV, raising=False)
    else:
        monkeypatch.setenv(h.CREATE_APP_HOOKS_ENV, val)
    app, calls = FastAPI(), []
    rep = h.apply_create_app_hooks(app, [_core_hook(calls)])
    assert rep["enabled"] is False and rep["applied"] == []
    assert calls == []
    assert getattr(app.state, "create_app_hooks_applied", False) is False


def test_off_by_default_even_when_registered_hook_cannot_import(monkeypatch):
    monkeypatch.delenv(h.CREATE_APP_HOOKS_ENV, raising=False)
    monkeypatch.setenv(h.CREATE_APP_HOOKS_STRICT_ENV, "1")
    monkeypatch.setattr(h, "CREATE_APP_HOOKS", ("no.such.module:x",))
    assert h.apply_create_app_hooks(FastAPI())["enabled"] is False


# --- enabled, default (error-isolated) mode: log, skip, keep booting ---

def test_isolated_install_failure_is_logged_and_skipped(monkeypatch, caplog):
    _enable(monkeypatch)
    app, calls = FastAPI(), []

    def boom(app):
        raise RuntimeError("bad hook")

    with caplog.at_level("WARNING", logger=h.__name__):
        rep = h.apply_create_app_hooks(app, [boom, _core_hook(calls)])
    assert rep["strict"] is False
    assert calls == [1] and len(rep["applied"]) == 1
    (name, err), = rep["errors"].items()
    assert name.endswith("boom") and err == "RuntimeError: bad hook"
    assert any("failed; skipped" in r.getMessage() for r in caplog.records)
    assert app.state.create_app_hooks_applied is True
    assert app.state.create_app_hooks_report is rep
    with TestClient(app) as c:  # the app still boots and serves the good hook
        assert c.get("/api/v1/core/ping").json() == {"ok": True}


def test_isolated_import_failure_is_logged_and_skipped(monkeypatch, caplog):
    _enable(monkeypatch)

    def marker_hook(app):
        app.state.marker = True

    monkeypatch.setattr(h, "_test_marker_hook", marker_hook, raising=False)
    monkeypatch.setattr(h, "CREATE_APP_HOOKS", (
        "no.such.module:x",
        "skeleton.gate_plane.create_app_hooks:_test_marker_hook",
    ))
    app = FastAPI()
    with caplog.at_level("WARNING", logger=h.__name__):
        rep = h.apply_create_app_hooks(app)
    assert app.state.marker is True
    assert [n.rsplit(".", 1)[-1] for n in rep["applied"]] == ["marker_hook"]
    assert list(rep["errors"]) == ["no.such.module:x"]
    assert rep["errors"]["no.such.module:x"].startswith("ModuleNotFoundError")
    assert any("failed to resolve; skipped" in r.getMessage() for r in caplog.records)
    with TestClient(app) as c:
        assert c.get("/nope").status_code == 404


def test_isolated_core_mount_without_backend_importable_still_boots(monkeypatch):
    """The real registered hook, with the Backend adapter missing, must not stop the app."""
    _enable(monkeypatch)
    import skeleton.gate_plane.core_mount as cm

    def missing_backend():
        raise ModuleNotFoundError("No module named 'routes'")

    monkeypatch.setattr(cm.install_core_v1, "__kwdefaults__",
                        {**cm.install_core_v1.__kwdefaults__, "loader": missing_backend})
    app = FastAPI()
    rep = h.apply_create_app_hooks(app)
    assert rep["applied"] == []
    assert list(rep["errors"]) == ["install_core_v1"]
    assert "ModuleNotFoundError" in rep["errors"]["install_core_v1"]
    assert getattr(app.state, "core_v1_mounted", False) is False
    with TestClient(app) as c:
        assert c.get("/api/v1/core/webhooks").status_code == 404


# --- enabled + strict mode: fail closed ---

@pytest.mark.parametrize("val", ["1", "true", "YES", "on"])
def test_strict_install_failure_aborts_app_construction(monkeypatch, val):
    _enable(monkeypatch, strict=val)
    app, calls = FastAPI(), []

    def boom(app):
        raise RuntimeError("bad hook")

    with pytest.raises(RuntimeError, match=r"required create_app hook \S*boom failed"):
        h.apply_create_app_hooks(app, [boom, _core_hook(calls)])
    assert calls == []
    assert getattr(app.state, "create_app_hooks_applied", False) is False


def test_strict_failure_after_partial_application_remains_fail_closed(monkeypatch):
    _enable(monkeypatch, strict="1")
    app, calls = FastAPI(), []

    def boom(app):
        raise RuntimeError("later hook failure")

    with pytest.raises(RuntimeError, match=r"required create_app hook \S*boom failed"):
        h.apply_create_app_hooks(app, [_core_hook(calls), boom])
    assert calls == [1]
    assert getattr(app.state, "create_app_hooks_applied", False) is False
    assert not hasattr(app.state, "create_app_hooks_report")


def test_strict_resolution_failure_aborts_app_construction(monkeypatch):
    _enable(monkeypatch, strict="1")
    monkeypatch.setattr(h, "CREATE_APP_HOOKS", ("no.such.module:x",))
    app = FastAPI()
    with pytest.raises(RuntimeError, match="required create_app hooks failed to resolve"):
        h.apply_create_app_hooks(app)
    assert getattr(app.state, "create_app_hooks_applied", False) is False


@pytest.mark.parametrize("val", ["", "0", "off"])
def test_strict_flag_values_that_do_not_enable_strict(monkeypatch, val):
    _enable(monkeypatch, strict=val)

    def boom(app):
        raise RuntimeError("bad hook")

    rep = h.apply_create_app_hooks(FastAPI(), [boom])
    assert rep["strict"] is False and list(rep["errors"])


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
