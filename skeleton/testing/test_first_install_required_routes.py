"""First-install readiness must not accept a healthy socket with missing API routes."""

from __future__ import annotations

import importlib
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest


def _mounted_registry(summary):
    from skeleton.app.first_install import CRITICAL_ROUTE_PATHS
    if not isinstance(summary, dict):
        return summary
    result = dict(summary)
    critical = result.get("critical_routes", {})
    missing = critical.get("missing", [])
    result.setdefault("mounted_names", [name for name in CRITICAL_ROUTE_PATHS if name not in missing])
    result.setdefault("mounted_paths", {name: [path] for name, path in CRITICAL_ROUTE_PATHS.items()
                                        if name not in missing})
    return result


def _doctor(monkeypatch, tmp_path, critical, *, providers=None, health_hook=None,
            route_hook=None, provider_hook=None, studio_hook=None, environ=None,
            manifest_hook=None):
    install = importlib.import_module("skeleton.app.first_install")
    health = importlib.import_module("skeleton.app.health")

    class Manifest:
        @staticmethod
        def service(name):
            return SimpleNamespace(public_url=f"http://127.0.0.1:8080/{name}")

    monkeypatch.setattr(install, "inspect_host", lambda root: SimpleNamespace(ready=True, checks=[]))
    monkeypatch.setattr(install, "preflight", lambda *a, **kw: [])
    monkeypatch.setattr(install, "checks_ok", lambda checks: True)
    monkeypatch.setattr(install, "_runtime_env", lambda *a, **kw: {
        "AI_PROVIDER": "local", "AI_LOCAL_MODEL_PATH": "model.bin",
    })
    monkeypatch.setattr(install, "load_manifest", Manifest)
    def runtime_manifest(manifest, **kw):
        if manifest_hook:
            manifest_hook(kw)
        return manifest

    def probe_application(**kw):
        if health_hook:
            health_hook()
        return []

    monkeypatch.setattr(install, "runtime_manifest", runtime_manifest)
    monkeypatch.setattr(health, "probe_application", probe_application)
    monkeypatch.setattr(health, "probes_ok", lambda probes: True)

    def bounded(url, *, timeout, max_response_bytes=65536):
        if url.endswith("/api/health/registry"):
            if route_hook:
                route_hook()
            return _mounted_registry(critical)
        if provider_hook:
            provider_hook()
        return providers if providers is not None else {
            "engine": "skeleton-engine", "providers": [],
            "llm_available": False, "availability_observed": True,
        }

    monkeypatch.setattr(install, "_bounded_json", bounded)
    if studio_hook:
        from skeleton.app import studio_readiness
        monkeypatch.setattr(studio_readiness, "studio_readiness_report", studio_hook)
    return install.first_install_report(tmp_path, live=True, studio=bool(studio_hook),
                                        environ=environ)


def test_first_install_rejects_unobservable_route_registry(monkeypatch, tmp_path):
    report = _doctor(monkeypatch, tmp_path, None)
    assert report["platform_ready"] is True
    assert report["configuration_ready"] is True
    assert report["services_ready"] is False
    assert report["critical_routes"]["observed"] is False
    assert any("critical_routes" in step for step in report["next_steps"])


def test_first_install_rejects_missing_critical_route(monkeypatch, tmp_path):
    report = _doctor(monkeypatch, tmp_path, {
        "critical_routes": {
            "ok": False, "report_available": True,
            "missing": ["routes.jeeves_media"],
        },
    })
    assert report["services_ready"] is False
    assert report["critical_routes"]["observed"] is True
    assert report["critical_routes"]["missing"] == ["routes.jeeves_media"]


def test_first_install_accepts_observed_required_routes(monkeypatch, tmp_path):
    report = _doctor(monkeypatch, tmp_path, {
        "critical_routes": {
            "ok": True, "report_available": True, "missing": [],
        },
    })
    assert report["services_ready"] is True
    assert report["critical_routes"]["ready"] is True


@pytest.mark.parametrize("code", ["local_guard_unavailable", "local_guard_configuration_invalid"])
def test_doctor_reports_observed_local_guard_problem_not_missing_weights(monkeypatch, tmp_path, code):
    report = _doctor(monkeypatch, tmp_path, {"critical_routes": {
        "ok": True, "report_available": True, "missing": [],
    }}, providers={
        "engine": "skeleton-engine", "active": "local", "providers": ["local"],
        "llm_available": False, "availability_observed": True, "active_readiness_code": code,
    })
    assert report["ai"]["readiness_code"] == code
    assert report["ai"]["available"] is False
    assert any("guard" in step.lower() for step in report["next_steps"])
    assert not any("Configure genuine trained local weights" in step for step in report["next_steps"])


@pytest.mark.parametrize("overrides", [
    {"active": "openai"}, {"llm_available": True}, {"availability_observed": False},
    {"active_readiness_code": "secret: do-not-print"}, {"active_readiness_code": ["invalid"]},
])
def test_doctor_ignores_untrusted_or_contradictory_guard_codes(monkeypatch, tmp_path, overrides):
    payload = {
        "engine": "skeleton-engine", "active": "local", "providers": ["local"],
        "llm_available": False, "availability_observed": True, "active_readiness_code": "local_guard_unavailable",
    }
    payload.update(overrides)
    report = _doctor(monkeypatch, tmp_path, {"critical_routes": {
        "ok": True, "report_available": True, "missing": [],
    }}, providers=payload)
    assert "readiness_code" not in report["ai"]
    assert "do-not-print" not in str(report)


def test_first_install_rejects_contradictory_ready_with_missing_routes(monkeypatch, tmp_path):
    report = _doctor(monkeypatch, tmp_path, {
        "critical_routes": {
            "ok": True, "report_available": True,
            "missing": ["routes.marketplace"],
        },
    })
    assert report["critical_routes"]["observed"] is True
    assert report["critical_routes"]["ready"] is False
    assert report["services_ready"] is False


def test_first_install_does_not_trust_malformed_route_report(monkeypatch, tmp_path):
    report = _doctor(monkeypatch, tmp_path, {
        "critical_routes": {
            "ok": True, "report_available": True, "missing": [123],
        },
    })
    assert report["services_ready"] is False
    assert report["critical_routes"]["observed"] is False


def _install_with_routes(monkeypatch, tmp_path, *, ready, backend_override=True, observed_urls=None):
    # The production installer now binds a stable private runtime file before
    # Compose. Keep this mocked route-registry fixture realistic rather than
    # bypassing a mandatory configuration custody gate.
    (tmp_path / ".env").write_text(
        "FRONTEND_PORT=3000\nBACKEND_PORT=8001\n", encoding="utf-8"
    )
    installer = importlib.import_module("skeleton.app.installer")
    health = importlib.import_module("skeleton.app.health")
    doctor = importlib.import_module("skeleton.app.first_install")

    class Manifest:
        def mode_env(self, mode):
            return {}

        def service(self, name):
            assert name == "backend"
            if backend_override:
                raise AssertionError("backend override must not evaluate fallback service")
            return SimpleNamespace(public_url="http://127.0.0.1:8099")

    monkeypatch.setattr(installer, "inspect_host", lambda *a, **kw: SimpleNamespace(checks=[]))
    monkeypatch.setattr(installer, "ensure_runtime_environment", lambda *a, **kw: SimpleNamespace(
        created=False, changed=False, env_path=tmp_path / ".env", configured_keys=[], warnings=[],
    ))
    monkeypatch.setattr(installer, "load_manifest", Manifest)
    monkeypatch.setattr(installer, "preflight", lambda *a, **kw: [])
    monkeypatch.setattr(installer, "checks_ok", lambda checks: True)
    monkeypatch.setattr(installer, "runtime_manifest", lambda manifest, **kw: manifest)
    monkeypatch.setattr(installer, "compose_command", lambda *a, **kw: ["docker", "compose"])
    monkeypatch.setattr(installer, "public_service_urls", lambda *a, **kw: (
        {"backend": "http://127.0.0.1:8001"} if backend_override else {}
    ))
    monkeypatch.setattr(health, "wait_for_application", lambda **kw: ())
    monkeypatch.setattr(health, "probes_ok", lambda results: True)
    def route_report(url, **kwargs):
        if observed_urls is not None:
            observed_urls.append(url)
        return {"ready": ready}

    monkeypatch.setattr(doctor, "critical_backend_route_report", route_report)

    def runner(args, **kwargs):
        return SimpleNamespace(returncode=0)

    return installer.install_application(tmp_path, start=True, install_python=False, runner=runner)


def test_install_receipt_refuses_success_with_missing_routes(monkeypatch, tmp_path):
    receipt = _install_with_routes(monkeypatch, tmp_path, ready=False)
    assert receipt.ok is False
    assert receipt.phases[-1].name == "critical-api-routes"
    assert receipt.phases[-1].ok is False
    assert all("credential" not in phase.detail.lower() for phase in receipt.phases[-1:])


def test_install_receipt_accepts_verified_required_routes(monkeypatch, tmp_path):
    receipt = _install_with_routes(monkeypatch, tmp_path, ready=True)
    assert receipt.ok is True
    assert receipt.phases[-1].name == "critical-api-routes"
    assert receipt.phases[-1].ok is True


@contextmanager
def _registry_server(payload):
    raw = json.dumps(payload).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass  # A bounded reader can close before an oversized body ends.

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_large_mounted_route_registry_is_observable_over_real_http():
    install = importlib.import_module("skeleton.app.first_install")
    payload = {
        "critical_routes": {"ok": True, "report_available": True, "missing": []},
        "mounted_routes": ["/api/studio/" + str(i) for i in range(7000)],
    }
    assert 65536 < len(json.dumps(payload).encode()) < 512 * 1024
    with _registry_server(_mounted_registry(payload)) as base:
        report = install.critical_backend_route_report(base, timeout=5)
    assert report["observed"] is True
    assert report["ready"] is True


def test_registry_allowance_remains_bounded_over_real_http():
    install = importlib.import_module("skeleton.app.first_install")
    payload = {
        "critical_routes": {"ok": True, "report_available": True, "missing": []},
        "padding": "x" * (512 * 1024),
    }
    with _registry_server(payload) as base:
        report = install.critical_backend_route_report(base, timeout=5)
    assert report["observed"] is False
    assert report["ready"] is False


def test_ordinary_readiness_keeps_small_response_bound_over_real_http():
    install = importlib.import_module("skeleton.app.first_install")
    with _registry_server({"padding": "x" * 70000}) as base:
        assert install._bounded_json(base + "/api/ai/providers", timeout=5) is None


def test_first_install_override_is_lazy_and_canonical_url_is_fallback_only(
    monkeypatch, tmp_path,
):
    explicit = []
    receipt = _install_with_routes(
        monkeypatch, tmp_path, ready=True, observed_urls=explicit,
    )
    assert receipt.ok is True
    assert explicit == ["http://127.0.0.1:8001"]

    fallback = []
    receipt = _install_with_routes(
        monkeypatch, tmp_path, ready=True,
        backend_override=False, observed_urls=fallback,
    )
    assert receipt.ok is True
    assert fallback == ["http://127.0.0.1:8099"]



_READY_ROUTES = {"critical_routes": {"ok": True, "report_available": True, "missing": []}}
_READY_AI = {"engine": "skeleton-engine", "active": "local", "providers": ["local"],
             "llm_available": True, "availability_observed": True}


@pytest.mark.parametrize("stage", ["health", "registry", "provider", "manifest"])
def test_doctor_disowns_evidence_across_runtime_configuration_epoch_change(
    monkeypatch, tmp_path, stage,
):
    config = tmp_path / ".env"
    config.write_text("AI_PROVIDER=local\n", encoding="utf-8")
    seen = []

    def change(*_args):
        seen.append(stage)
        config.write_text("AI_PROVIDER=openai\n", encoding="utf-8")

    def forbidden():
        pytest.fail("further probe used a configuration epoch already rejected")

    hooks = {
        "health_hook": change if stage == "health" else forbidden if stage == "manifest" else None,
        "route_hook": change if stage == "registry" else forbidden if stage in ("health", "manifest") else None,
        "provider_hook": change if stage == "provider" else forbidden if stage in ("health", "registry", "manifest") else None,
        "manifest_hook": change if stage == "manifest" else None,
    }
    result = _doctor(monkeypatch, tmp_path, _READY_ROUTES, providers=_READY_AI, **hooks)
    assert seen == [stage]
    assert result["configuration_ready"] is False
    assert result["services_ready"] is None
    assert result["ai_ready"] is False
    assert result["ai"]["observed"] is False and result["ai"]["available"] is None
    assert result["critical_routes"]["observed"] is False
    assert result["checks"]["live"] == []


def test_doctor_does_not_keep_authenticated_crawler_facts_after_config_change(monkeypatch, tmp_path):
    config = tmp_path / ".env"
    config.write_text("AI_PROVIDER=local\n", encoding="utf-8")

    def studio(_root, **kw):
        assert kw["live"] is True
        config.write_text("AI_PROVIDER=openai\n", encoding="utf-8")
        return {"local_host": {"observed": True}, "server": {
            "observed": True,
            "crawler": {"observed": True, "report": {
                "available": True, "configured": True, "code": "ready",
            }},
        }}

    result = _doctor(monkeypatch, tmp_path, _READY_ROUTES, providers=_READY_AI, studio_hook=studio)
    assert result["ai_ready"] is False
    assert result["crawler"]["observed"] is False
    assert result["crawler"]["available"] is None
    assert "code" not in result["crawler"]
    assert result["studio"]["server"]["crawler"]["observed"] is False


def test_doctor_stabilizes_process_environment_overrides(monkeypatch, tmp_path):
    overrides = {"AI_PROVIDER": "local"}
    seen = []

    def inspect_manifest(kw):
        overrides["AI_PROVIDER"] = "openai"
        seen.append(kw["environ"]["AI_PROVIDER"])

    result = _doctor(monkeypatch, tmp_path, _READY_ROUTES, providers=_READY_AI,
                     environ=overrides, manifest_hook=inspect_manifest)
    assert seen == ["local"]
    assert result["ai_ready"] is True


def test_doctor_refuses_new_env_appearing_during_probe(monkeypatch, tmp_path):
    def create():
        (tmp_path / ".env").write_text("AI_PROVIDER=local\n", encoding="utf-8")

    result = _doctor(monkeypatch, tmp_path, _READY_ROUTES, providers=_READY_AI, health_hook=create)
    assert result["configuration_ready"] is False
    assert result["services_ready"] is None
    assert result["ai_ready"] is False


@pytest.mark.parametrize("url", [
    "http://user:secret@localhost/api/health", "http://localhost:bad/api/health",
    "http://localhost:0/api/health", "http://[::1/api/health",
    "http://localhost/api/health?", "http://localhost/api/health#",
    "http://local%68ost/api/health", "http://localhost/api/health\n",
    "file:///etc/passwd", "",
])
def test_doctor_json_admission_rejects_invalid_urls_before_worker(monkeypatch, url):
    install = importlib.import_module("skeleton.app.first_install")
    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid diagnostic origin reached worker")
    monkeypatch.setattr("skeleton.app.studio_readiness._bounded_server", forbidden)
    assert install._bounded_json(url, timeout=1) is None



def test_critical_route_contract_matches_backend_source():
    import ast
    from pathlib import Path
    from skeleton.app.first_install import CRITICAL_ROUTE_PATHS
    source = Path(__file__).resolve().parents[2] / "backend/routes/registry_health.py"
    assignments = [node for node in ast.parse(source.read_text(encoding="utf-8")).body
                   if isinstance(node, ast.AnnAssign)
                   and isinstance(node.target, ast.Name) and node.target.id == "CRITICAL_ROUTE_PATHS"]
    assert len(assignments) == 1
    assert ast.literal_eval(assignments[0].value) == CRITICAL_ROUTE_PATHS


@pytest.mark.parametrize("missing", [
    ["routes.unknown"], ["token:private-value"], ["routes.jeeves_media"]*2, [True], [{}],
])
def test_unknown_duplicate_or_sensitive_route_names_never_escape(missing):
    from skeleton.app.first_install import critical_route_evidence
    result = critical_route_evidence({"critical_routes":{
        "ok":False,"report_available":True,"missing":missing,
    }})
    assert result == (False, False, [])


@pytest.mark.parametrize("field", ["mounted_names", "mounted_paths"])
def test_positive_summary_without_mount_inventory_is_unqualified(field):
    from skeleton.app.first_install import critical_route_evidence
    payload = _mounted_registry({"critical_routes":{"ok":True,"report_available":True,"missing":[]}})
    payload.pop(field)
    assert critical_route_evidence(payload) == (False, False, [])


@pytest.mark.parametrize("mutation", ["name", "path", "wrong_path", "malformed"])
def test_false_positive_router_summary_is_denied_by_positive_mount_evidence(mutation):
    from skeleton.app.first_install import critical_route_evidence
    payload = _mounted_registry({"critical_routes":{"ok":True,"report_available":True,"missing":[]}})
    name = "routes.jeeves_media"
    if mutation == "name":
        payload["mounted_names"].remove(name)
    elif mutation == "path":
        payload["mounted_paths"].pop(name)
    elif mutation == "wrong_path":
        payload["mounted_paths"][name] = ["/api/wrong"]
    else:
        payload["mounted_paths"][name] = [42]
    assert critical_route_evidence(payload) == (True, False, [name])


def test_unavailable_registry_never_returns_positive_readiness():
    from skeleton.app.first_install import critical_route_evidence
    payload = _mounted_registry({"critical_routes":{"ok":True,"report_available":False,"missing":[]}})
    assert critical_route_evidence(payload) == (False, False, [])



@pytest.mark.parametrize("code,available,configured",[
    ("reflected-private-value",True,True),("ready",True,False),
    ("ready",False,True),("crawler_indexes_unavailable",True,True),
])
def test_doctor_crawler_projection_rejects_contradictory_or_unreviewed_code(
    monkeypatch,tmp_path,code,available,configured
):
    def studio(*args,**kwargs):
        return {"server":{"crawler":{"observed":True,"report":{
            "available":available,"configured":configured,"code":code,
        }}}}
    result=_doctor(monkeypatch,tmp_path,_READY_ROUTES,providers=_READY_AI,studio_hook=studio)
    assert result["crawler"]["observed"] is False
    assert "code" not in result["crawler"]


def test_doctor_sticky_epoch_rejection_even_if_absent_source_returns(monkeypatch,tmp_path):
    config=tmp_path/".env"
    def health():
        config.write_text("VALUE=transient\n")
    def studio(*args,**kwargs):
        # A callback after the rejected epoch must not re-open the live lane.
        config.unlink()
        assert kwargs["admit_live"]() is False
        assert kwargs["live"] is False
        return {"server":{"crawler":{"observed":False}}}
    result=_doctor(monkeypatch,tmp_path,_READY_ROUTES,providers=_READY_AI,
                   health_hook=health,studio_hook=studio)
    assert result["configuration_ready"] is False
    assert result["endpoints"]=={}
    assert not any("app up" in step for step in result["next_steps"])
