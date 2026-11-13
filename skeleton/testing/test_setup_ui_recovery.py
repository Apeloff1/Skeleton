"""Installer setup-only recovery must never launder a failed protected start.

These tests use a deterministic Compose runner. They are not Windows/Docker
qualification and never count setup liveness as authenticated game readiness.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from skeleton.app import installer
from skeleton.app.assembly import load_manifest
from skeleton.app.health import ProbeResult
from skeleton.app.preloader import PreloadReport
from skeleton.app.setup_runtime import SetupResult


def _run_install(tmp_path: Path, monkeypatch, *, independent: bool, recovery_ok: bool = True,
                 setup_ok: bool = True, real_bootstrap: bool = False):
    manifest = load_manifest()
    if independent:
        services = tuple(
            replace(item, depends_on=()) if item.name == "frontend" else item
            for item in manifest.services
        )
        manifest = replace(manifest, services=services)
    else:
        services = tuple(
            replace(item, depends_on=("backend",)) if item.name == "frontend" else item
            for item in manifest.services
        )
        manifest = replace(manifest, services=services)
    monkeypatch.setattr(installer, "load_manifest", lambda: manifest)
    monkeypatch.setattr(
        installer, "inspect_host",
        lambda *args, **kwargs: PreloadReport(
            root=tmp_path, platform="test", python=sys.executable, checks=()
        ),
    )
    if real_bootstrap:
        # Exercise the actual secret-bootstrap implementation, not a mocked
        # setup receipt. Only Compose and HTTP are simulated in this test.
        (tmp_path / ".env.example").write_text(
            "MONGO_INITDB_ROOT_USERNAME=admin\n"
            "MONGO_INITDB_ROOT_PASSWORD=\n"
            "JWT_SECRET=\n"
            "AI_PROVIDER=local\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("SKELETON_LOCAL_MODEL_DIR", str(tmp_path / "local-models"))
    else:
        monkeypatch.setattr(
            installer, "ensure_runtime_environment",
            lambda *args, **kwargs: SetupResult(
                env_path=tmp_path / ".env", created=False, changed=False,
                configured_keys=(), preserved_keys=(), warnings=()
            ),
        )
    monkeypatch.setattr(installer, "preflight", lambda *args, **kwargs: ())
    monkeypatch.setattr(installer, "runtime_manifest", lambda m, **kwargs: m)
    monkeypatch.setattr(
        installer, "public_service_urls",
        lambda *args, **kwargs: {
            "frontend": "http://127.0.0.1:3000",
            "backend": "http://127.0.0.1:8001",
            "skeleton": "http://127.0.0.1:8010",
        },
    )
    calls = []
    def runner(command, **kwargs):
        calls.append((tuple(command), kwargs))
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        if "config" in command:
            return subprocess.CompletedProcess(command, 0)
        assert "up" in command
        return subprocess.CompletedProcess(
            command, 0 if "backend" not in command and recovery_ok else 1
        )
    observed = []
    def probe(service, *, timeout):
        observed.append((service.name, service.public_url, service.health_path, timeout))
        return ProbeResult(
            service=service.name, url=service.public_url + "/setup",
            ok=setup_ok, status=200 if setup_ok else 404,
            detail="healthy" if setup_ok else "HTTP error 404",
        )
    monkeypatch.setattr("skeleton.app.health.probe_local_setup", probe)
    receipt = installer.install_application(
        tmp_path, install_python=False, start=True, runner=runner
    )
    return receipt, calls, observed


def test_failed_protected_start_can_recover_only_independent_setup_ui(tmp_path, monkeypatch):
    receipt, calls, observed = _run_install(tmp_path, monkeypatch, independent=True)
    assert not receipt.ok
    phases = {phase.name: phase for phase in receipt.phases}
    assert not phases["start"].ok and phases["start"].required
    assert phases["setup-ui-recovery"].ok and not phases["setup-ui-recovery"].required
    assert phases["setup-ui-availability"].ok and not phases["setup-ui-availability"].required
    assert observed == [("frontend", "http://127.0.0.1:3000", "/setup", 2.0)]
    ups = [cmd for cmd, _ in calls if "up" in cmd]
    assert len(ups) == 2
    assert "backend" in ups[0] and "skeleton" in ups[0]
    assert ups[1][-1] == "frontend" and "backend" not in ups[1]
    assert "readiness" not in phases
    assert "critical-api-routes" not in phases


def test_failed_protected_start_never_bypasses_frontend_dependency(tmp_path, monkeypatch):
    receipt, calls, observed = _run_install(tmp_path, monkeypatch, independent=False)
    assert not receipt.ok
    ups = [cmd for cmd, _ in calls if "up" in cmd]
    assert len(ups) == 1
    assert not observed
    phase = next(p for p in receipt.phases if p.name == "setup-ui-recovery")
    assert not phase.ok and not phase.required
    assert "#4682" in phase.detail


def test_recovery_command_failure_remains_unavailable(tmp_path, monkeypatch):
    receipt, calls, observed = _run_install(
        tmp_path, monkeypatch, independent=True, recovery_ok=False
    )
    assert not receipt.ok and not observed
    assert len([cmd for cmd, _ in calls if "up" in cmd]) == 2
    assert not next(p for p in receipt.phases if p.name == "setup-ui-recovery").ok
    assert not any(p.name == "setup-ui-availability" for p in receipt.phases)


def test_recovery_requires_actual_setup_route_probe(tmp_path, monkeypatch):
    receipt, _, observed = _run_install(
        tmp_path, monkeypatch, independent=True, setup_ok=False
    )
    assert not receipt.ok and observed
    phase = next(p for p in receipt.phases if p.name == "setup-ui-availability")
    assert not phase.ok and not phase.required
    assert "unavailable" in phase.detail


def test_real_secret_bootstrap_survives_failed_start_and_setup_only_restart(tmp_path, monkeypatch):
    """Integration acceptance: real setup custody + installer recovery.

    Compose and HTTP are deterministic fakes, not clean-host/device evidence.
    """
    first, commands, probes = _run_install(
        tmp_path, monkeypatch, independent=True, real_bootstrap=True
    )
    assert not first.ok
    assert probes == [("frontend", "http://127.0.0.1:3000", "/setup", 2.0)]
    assert len([command for command, _ in commands if "up" in command]) == 2
    env = tmp_path / ".env"
    initial = env.read_bytes()
    assert b"SKL_ENGINE_SERVICE_TOKEN=" in initial
    assert b"SKELETON_MASTER_SECRET=" in initial
    assert b"GF_KEYHOLDER_SEED=" in initial
    assert not any(phase.name == "readiness" for phase in first.phases)
    second, _, second_probes = _run_install(
        tmp_path, monkeypatch, independent=True, real_bootstrap=True
    )
    assert not second.ok and second_probes
    assert env.read_bytes() == initial
    for receipt in (first, second):
        phases = {phase.name: phase for phase in receipt.phases}
        assert phases["start"].required and not phases["start"].ok
        assert phases["setup-ui-recovery"].ok and not phases["setup-ui-recovery"].required
        assert phases["setup-ui-availability"].ok and not phases["setup-ui-availability"].required
        assert "critical-api-routes" not in phases
        assert "SKL_ENGINE_SERVICE_TOKEN=" not in repr(receipt.to_dict())
