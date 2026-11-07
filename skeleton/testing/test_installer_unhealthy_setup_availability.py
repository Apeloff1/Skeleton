"""Regression: unhealthy protected runtime must not hide the independent setup route."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from skeleton.app.installer import install_application
from skeleton.app.preloader import PreloadCheck, PreloadReport
from skeleton.app.setup_runtime import SetupResult


@pytest.mark.parametrize("setup_available", [True, False])
def test_unhealthy_backend_keeps_required_failure_and_probes_setup(tmp_path, monkeypatch, setup_available):
    import skeleton.app.installer as installer
    import skeleton.app.health as health

    monkeypatch.setattr(installer, "inspect_host", lambda root, runner, **kw: PreloadReport(
        root=tmp_path, platform="test", python="3.11",
        checks=(PreloadCheck("host:ready", True, "ready"),),
    ))
    monkeypatch.setattr(installer, "ensure_runtime_environment", lambda *a, **kw: SetupResult(
        tmp_path / ".env", False, False, (), (), (),
    ))
    monkeypatch.setattr(installer, "preflight", lambda *a, **kw: ())
    monkeypatch.setattr(installer, "checks_ok", lambda checks: True)
    monkeypatch.setattr(installer, "public_service_urls", lambda *a, **kw: {
        "frontend": "http://127.0.0.1:3000", "backend": "http://127.0.0.1:8000",
    })
    monkeypatch.setattr(installer, "compose_command", lambda action, **kw: (
        "docker", "compose", action,
    ))
    monkeypatch.setattr(health, "wait_for_application", lambda **kw: (
        SimpleNamespace(service="backend", ok=False),
    ))
    monkeypatch.setattr(health, "probes_ok", lambda results: False)
    observed = []

    def probe(frontend, *, timeout):
        observed.append((frontend.health_path, timeout))
        return SimpleNamespace(ok=setup_available)

    monkeypatch.setattr(health, "probe_local_setup", probe)
    runner = lambda command, **kw: subprocess.CompletedProcess(command, 0)
    receipt = install_application(tmp_path, install_python=False, start=True, runner=runner)
    assert not receipt.ok
    required = [phase for phase in receipt.phases if phase.name == "readiness"]
    assert len(required) == 1 and required[0].required and not required[0].ok
    availability = [phase for phase in receipt.phases if phase.name == "setup-ui-availability"]
    assert len(availability) == 1
    assert availability[0].ok is setup_available
    assert availability[0].required is False
    assert "protected runtime remains unhealthy" in availability[0].detail
    assert observed == [("/setup", 2.0)]
