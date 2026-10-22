"""First-install readiness must not accept a healthy socket with missing API routes."""

from __future__ import annotations

import importlib
from types import SimpleNamespace


def _doctor(monkeypatch, tmp_path, critical):
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
    monkeypatch.setattr(install, "runtime_manifest", lambda manifest, **kw: manifest)
    monkeypatch.setattr(health, "probe_application", lambda **kw: [])
    monkeypatch.setattr(health, "probes_ok", lambda probes: True)

    def bounded(url, *, timeout):
        if url.endswith("/api/health/registry"):
            return critical
        return {
            "engine": "skeleton-engine", "providers": [],
            "llm_available": False, "availability_observed": True,
        }

    monkeypatch.setattr(install, "_bounded_json", bounded)
    return install.first_install_report(tmp_path, live=True)


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


def test_first_install_does_not_trust_malformed_route_report(monkeypatch, tmp_path):
    report = _doctor(monkeypatch, tmp_path, {
        "critical_routes": {
            "ok": True, "report_available": True, "missing": [123],
        },
    })
    assert report["services_ready"] is False
    assert report["critical_routes"]["observed"] is False


def _install_with_routes(monkeypatch, tmp_path, *, ready):
    installer = importlib.import_module("skeleton.app.installer")
    health = importlib.import_module("skeleton.app.health")
    doctor = importlib.import_module("skeleton.app.first_install")

    class Manifest:
        def mode_env(self, mode):
            return {}

    monkeypatch.setattr(installer, "inspect_host", lambda *a, **kw: SimpleNamespace(checks=[]))
    monkeypatch.setattr(installer, "ensure_runtime_environment", lambda *a, **kw: SimpleNamespace(
        created=False, changed=False, env_path=tmp_path / ".env", configured_keys=[], warnings=[],
    ))
    monkeypatch.setattr(installer, "load_manifest", Manifest)
    monkeypatch.setattr(installer, "preflight", lambda *a, **kw: [])
    monkeypatch.setattr(installer, "checks_ok", lambda checks: True)
    monkeypatch.setattr(installer, "runtime_manifest", lambda manifest, **kw: manifest)
    monkeypatch.setattr(installer, "compose_command", lambda *a, **kw: ["docker", "compose"])
    monkeypatch.setattr(installer, "public_service_urls", lambda *a, **kw: {
        "backend": "http://127.0.0.1:8001",
    })
    monkeypatch.setattr(health, "wait_for_application", lambda **kw: ())
    monkeypatch.setattr(health, "probes_ok", lambda results: True)
    monkeypatch.setattr(doctor, "critical_backend_route_report", lambda *a, **kw: {"ready": ready})

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
