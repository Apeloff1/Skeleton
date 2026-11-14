"""Regression: malformed diagnostic Compose must preserve failed install receipt."""

from __future__ import annotations

import subprocess
from pathlib import Path

from skeleton.app.installer import install_application
from skeleton.app.preloader import PreloadCheck, PreloadReport
from skeleton.app.setup_runtime import SetupResult


def test_diagnostic_compose_error_does_not_escape_or_hide_primary_failure(tmp_path, monkeypatch):
    import skeleton.app.installer as installer

    monkeypatch.setattr(
        installer, "inspect_host",
        lambda root, runner, **kwargs: PreloadReport(
            root=tmp_path, platform="test", python="3.11",
            checks=(PreloadCheck("host:ready", True, "ready"),),
        ),
    )
    monkeypatch.setattr(
        installer, "ensure_runtime_environment",
        lambda *args, **kwargs: SetupResult(tmp_path / ".env", False, False, (), (), ()),
    )
    monkeypatch.setattr(installer, "preflight", lambda *args, **kwargs: ())
    monkeypatch.setattr(installer, "checks_ok", lambda checks: True)
    monkeypatch.setattr(
        installer, "public_service_urls",
        lambda *args, **kwargs: {"frontend": "http://127.0.0.1:3000", "backend": "http://127.0.0.1:8000"},
    )
    real_compose = installer.compose_command

    def compose(action, **kwargs):
        if action == "up" and kwargs.get("manifest").default_services == ("frontend",):
            raise ValueError("private invalid diagnostic topology")
        return ("docker", "compose", action)

    monkeypatch.setattr(installer, "compose_command", compose)
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 2 if command[-1] == "up" else 0)

    receipt = install_application(tmp_path, install_python=False, start=True, runner=runner)
    assert not receipt.ok
    assert any(p.name == "start" and not p.ok and p.required for p in receipt.phases)
    recovery = [p for p in receipt.phases if p.name == "setup-ui-recovery"]
    assert len(recovery) == 1
    assert recovery[0].required is False
    assert recovery[0].ok is False
    assert "private invalid diagnostic topology" not in repr(receipt.to_dict())
