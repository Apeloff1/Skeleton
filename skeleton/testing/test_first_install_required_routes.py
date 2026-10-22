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
