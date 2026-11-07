"""Installer failures must yield bounded, redacted receipts without starting services."""
from __future__ import annotations

import subprocess

import pytest

from skeleton.app import installer
from skeleton.app.preloader import PreloadCheck, PreloadReport
from skeleton.app.setup_runtime import SetupResult


@pytest.fixture
def ready_installer(tmp_path, monkeypatch):
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
        "docker", "compose", action, "frontend",
    ))
    calls = []

    def runner(command, **kwargs):
        calls.append(tuple(command))
        return subprocess.CompletedProcess(command, 0)

    return tmp_path, runner, calls


@pytest.mark.parametrize(
    ("stage", "expected_phase"),
    [
        ("load_manifest", "manifest"),
        ("preflight", "runtime-preflight"),
        ("runtime_manifest", "runtime-manifest"),
        ("compose_command", "compose-config"),
    ],
)
def test_broken_contract_fails_closed_with_redacted_receipt(
    ready_installer, monkeypatch, stage, expected_phase
):
    root, runner, calls = ready_installer
    secret = "operator-password-in-untrusted-error"
    def broken(*args, **kwargs):
        raise ValueError(secret)

    monkeypatch.setattr(installer, stage, broken)
    receipt = installer.install_application(root, install_python=False, start=True, runner=runner)
    assert not receipt.ok
    assert receipt.phases[-1].name == expected_phase
    assert receipt.phases[-1].required and not receipt.phases[-1].ok
    assert secret not in str(receipt.to_dict())
    assert calls == []


@pytest.mark.parametrize(
    ("stage", "expected_phase"),
    [("public_service_urls", "public-endpoints"), ("compose_command", "start")],
)
def test_startup_contract_error_never_leaks_private_configuration(
    ready_installer, monkeypatch, stage, expected_phase
):
    root, runner, calls = ready_installer
    secret = "sensitive-local-configuration"
    if stage == "compose_command":
        def command(action, **kwargs):
            if action == "up":
                raise ValueError(secret)
            return ("docker", "compose", action)
        monkeypatch.setattr(installer, stage, command)
    else:
        def broken(*args, **kwargs):
            raise ValueError(secret)
        monkeypatch.setattr(installer, stage, broken)

    receipt = installer.install_application(root, install_python=False, start=True, runner=runner)
    assert not receipt.ok
    assert receipt.phases[-1].name == expected_phase
    assert secret not in str(receipt.to_dict())
    assert len(calls) == 1  # validation only; no service startup
