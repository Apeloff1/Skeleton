"""Bounded first-install configuration epoch and preflight admission regression tests.

These are source-only tests: no Docker subprocess, live service, account,
device, or untrusted model is started. Fake runners deliberately simulate
concurrent operator configuration changes at each installation boundary.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from skeleton.app import installer
from skeleton.app.preloader import PreloadCheck, PreloadReport
from skeleton.app.setup_runtime import SetupResult, runtime_source_fingerprint


def _prepare(monkeypatch, tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text("FRONTEND_PORT=3000\nBACKEND_PORT=8001\n", encoding="utf-8")
    for key in ("FRONTEND_PORT", "BACKEND_PORT", "SKELETON_PORT", "MONGO_PORT", "CHROMA_PORT"):
        monkeypatch.delenv(key, raising=False)
    host = PreloadReport(
        root=tmp_path, platform="Windows", python="bundled",
        checks=(PreloadCheck("host:ready", True, "ready"),),
    )
    monkeypatch.setattr(installer, "inspect_host", lambda *args, **kwargs: host)
    monkeypatch.setattr(
        installer, "ensure_runtime_environment",
        lambda *args, **kwargs: SetupResult(env, False, False, (), (), ()),
    )
    monkeypatch.setattr(installer, "preflight", lambda *args, **kwargs: ())
    monkeypatch.setattr(installer, "checks_ok", lambda checks: True)
    monkeypatch.setattr(
        installer, "compose_command",
        lambda action, **kwargs: ("docker", "compose", action),
    )
    return env


def _completed(command):
    return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def _forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("runtime config drift must not permit health/route network probes")
    monkeypatch.setattr("skeleton.app.health.wait_for_application", forbidden)
    monkeypatch.setattr(
        "skeleton.app.first_install.critical_backend_route_report", forbidden,
    )


def test_source_fingerprint_is_stable_bounded_and_redacts_private_values(tmp_path):
    env = tmp_path / ".env"
    private = "first-install-private-secret-never-in-receipts"
    env.write_text("JWT_SECRET=" + private + "\n", encoding="utf-8")
    first = runtime_source_fingerprint(tmp_path)
    second = runtime_source_fingerprint(tmp_path)
    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert private not in first
    assert private == env.read_text(encoding="utf-8").split("=", 1)[1].strip()
    env.write_text("JWT_SECRET=" + private + "-changed\n", encoding="utf-8")
    assert first != runtime_source_fingerprint(tmp_path)


@pytest.mark.parametrize(
    ("invalid", "contents"),
    [
        ("oversized", b"A" * (256 * 1024 + 1)),
        ("invalid-utf8", b"\xff\xfe"),
    ],
)
def test_source_fingerprint_rejects_untrusted_file_without_returning_values(
    tmp_path, invalid, contents
):
    (tmp_path / ".env").write_bytes(contents)
    with pytest.raises(ValueError, match="runtime configuration source"):
        runtime_source_fingerprint(tmp_path)


def test_source_fingerprint_rejects_symlink_before_following_it(tmp_path):
    target = tmp_path / "external-operator-private"
    target.write_text("JWT_SECRET=external-value\n", encoding="utf-8")
    try:
        (tmp_path / ".env").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(ValueError, match="runtime configuration source"):
        runtime_source_fingerprint(tmp_path)
    assert target.read_text(encoding="utf-8") == "JWT_SECRET=external-value\n"


def test_source_fingerprint_rejects_unaliased_policy_violation(tmp_path):
    if os.name == "nt":
        pytest.skip("Windows hardlink custody uses ACL authority")
    operator = tmp_path / "private"
    operator.write_text("JWT_SECRET=do-not-adopt\n", encoding="utf-8")
    os.link(operator, tmp_path / ".env")
    with pytest.raises(ValueError, match="runtime configuration source"):
        runtime_source_fingerprint(tmp_path)


def test_changed_runtime_configuration_during_manifest_resolution_is_rejected(
    tmp_path, monkeypatch
):
    env = _prepare(monkeypatch, tmp_path)
    _forbid_network(monkeypatch)
    real = installer.runtime_manifest

    def mutating_resolver(*args, **kwargs):
        result = real(*args, **kwargs)
        env.write_text("FRONTEND_PORT=3300\nBACKEND_PORT=8001\n", encoding="utf-8")
        return result

    monkeypatch.setattr(installer, "runtime_manifest", mutating_resolver)

    def forbidden_runner(*args, **kwargs):
        pytest.fail("manifest-source mutation must block Compose validation")

    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=forbidden_runner,
    )
    assert receipt.ok is False
    assert receipt.phases[-1].name == "runtime-source-epoch"
    assert "FRONTEND_PORT" not in receipt.phases[-1].detail
    assert "3300" not in repr(receipt.to_dict())


def test_changed_runtime_configuration_during_compose_config_aborts_before_up(
    tmp_path, monkeypatch
):
    env = _prepare(monkeypatch, tmp_path)
    _forbid_network(monkeypatch)
    calls = []

    def runner(command, **kwargs):
        calls.append(tuple(command))
        if command[-1] == "config":
            env.write_text("FRONTEND_PORT=3300\nBACKEND_PORT=8001\n", encoding="utf-8")
        return _completed(command)

    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=runner,
    )
    assert receipt.ok is False
    assert [cmd[-1] for cmd in calls] == ["config"]
    assert receipt.phases[-1].name == "runtime-source-epoch"
    assert "3300" not in repr(receipt.to_dict())


def test_changed_runtime_configuration_during_docker_up_never_qualifies_readiness(
    tmp_path, monkeypatch
):
    env = _prepare(monkeypatch, tmp_path)
    _forbid_network(monkeypatch)
    calls = []

    def runner(command, **kwargs):
        calls.append(tuple(command))
        if command[-1] == "up":
            env.write_text("FRONTEND_PORT=3300\nBACKEND_PORT=8001\n", encoding="utf-8")
        return _completed(command)

    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=runner,
    )
    assert receipt.ok is False
    assert [cmd[-1] for cmd in calls] == ["config", "up"]
    assert receipt.phases[-1].name == "runtime-source-epoch"
    assert not any(p.name == "readiness" for p in receipt.phases)


def test_changed_runtime_configuration_during_health_disables_route_check(
    tmp_path, monkeypatch
):
    env = _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "skeleton.app.first_install.critical_backend_route_report",
        lambda *args, **kwargs: pytest.fail("route check must not run after env drift"),
    )

    class Probe:
        service = "backend"
        ok = True

    def mutating_health(**kwargs):
        env.write_text("FRONTEND_PORT=3300\nBACKEND_PORT=8001\n", encoding="utf-8")
        return (Probe(),)

    monkeypatch.setattr(
        "skeleton.app.health.wait_for_application", mutating_health,
    )
    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=lambda command, **kwargs: _completed(command),
    )
    assert not receipt.ok
    assert receipt.phases[-1].name == "runtime-source-epoch"
    assert not any(p.name == "critical-api-routes" for p in receipt.phases)


def test_runtime_source_invalid_during_manifest_resolution_returns_redacted_failure(
    tmp_path, monkeypatch
):
    _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(
        installer, "runtime_manifest",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("runtime private operator credential should not be logged")
        ),
    )

    def forbidden_runner(*args, **kwargs):
        pytest.fail("invalid manifest must block Compose")

    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=forbidden_runner,
    )
    assert not receipt.ok
    assert receipt.phases[-1].name == "runtime-manifest"
    assert "private operator credential" not in repr(receipt.to_dict())


def test_unchanged_runtime_epoch_permits_focused_readiness_and_route_validation(
    tmp_path, monkeypatch
):
    _prepare(monkeypatch, tmp_path)
    from skeleton.app.health import ProbeResult

    monkeypatch.setattr(
        "skeleton.app.health.wait_for_application",
        lambda **kwargs: (
            ProbeResult("backend", "http://localhost:8001", True, 200, "healthy"),
        ),
    )
    called = []
    monkeypatch.setattr(
        "skeleton.app.first_install.critical_backend_route_report",
        lambda url, **kwargs: called.append(url) or {"ready": True},
    )
    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=lambda cmd, **kwargs: _completed(cmd),
    )
    assert receipt.ok, receipt.to_dict()
    assert called == ["http://localhost:8001"]
    assert [phase.name for phase in receipt.phases if phase.name == "critical-api-routes"] == [
        "critical-api-routes"
    ]


def test_preflight_has_one_canonical_image_build_input_gate():
    from skeleton.app.assembly import find_repo_root, preflight

    root = find_repo_root(Path(__file__))
    image_checks = [
        check for check in preflight(root, runtime=False)
        if check.code == "image:build-inputs"
    ]
    assert len(image_checks) == 1, "duplicate source scan masks gate identity and increases startup cost"
    assert image_checks[0].ok, image_checks[0].message


def test_source_epoch_fences_same_bytes_different_inode(tmp_path):
    env = tmp_path / ".env"
    env.write_text("JWT_SECRET=redacted-local-fixture\n", encoding="utf-8")
    original = runtime_source_fingerprint(tmp_path)
    replacement = tmp_path / ".replacement"
    replacement.write_bytes(env.read_bytes())
    os.replace(replacement, env)
    assert original != runtime_source_fingerprint(tmp_path)


def test_source_epoch_fences_same_inode_metadata_rewrite(tmp_path):
    env = tmp_path / ".env"
    env.write_text("JWT_SECRET=redacted-local-fixture\n", encoding="utf-8")
    original = runtime_source_fingerprint(tmp_path)
    stat_before = env.stat()
    os.utime(env, ns=(
        stat_before.st_atime_ns, stat_before.st_mtime_ns + 2_000_000_000,
    ))
    assert env.read_bytes() == b"JWT_SECRET=redacted-local-fixture\n"
    assert original != runtime_source_fingerprint(tmp_path)


def test_identical_byte_replacement_after_compose_config_denies_docker_start(
    tmp_path, monkeypatch,
):
    env = _prepare(monkeypatch, tmp_path)
    _forbid_network(monkeypatch)
    seen = []

    def runner(command, **kwargs):
        seen.append(command[-1])
        if command[-1] == "config":
            replacement = tmp_path / "operator-equivalent-env"
            replacement.write_bytes(env.read_bytes())
            os.replace(replacement, env)
        return _completed(command)

    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=runner,
    )
    assert receipt.ok is False
    assert seen == ["config"]
    assert receipt.phases[-1].name == "runtime-source-epoch"
    assert "redacted-local-fixture" not in repr(receipt.to_dict())


def test_setup_ui_recovery_rejects_same_byte_epoch_swap_before_probe(
    tmp_path, monkeypatch,
):
    env = _prepare(monkeypatch, tmp_path)
    _forbid_network(monkeypatch)
    monkeypatch.setattr(
        "skeleton.app.health.probe_local_setup",
        lambda *args, **kwargs: pytest.fail(
            "changed config must prevent setup availability probe"
        ),
    )
    commands = []

    def runner(command, **kwargs):
        action = command[-1]
        commands.append(action)
        if action == "up" and commands.count("up") == 1:
            return subprocess.CompletedProcess(command, 9)
        if action == "up" and commands.count("up") == 2:
            replacement = tmp_path / "operator-replacement"
            replacement.write_bytes(env.read_bytes())
            os.replace(replacement, env)
        return _completed(command)

    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=runner,
    )
    assert receipt.ok is False
    assert commands == ["config", "up", "up"]
    assert receipt.phases[-1].name == "runtime-source-epoch"
    assert not any(p.name == "setup-ui-availability" for p in receipt.phases)


def test_setup_ui_probe_mutating_private_epoch_never_attests_availability(
    tmp_path, monkeypatch,
):
    env = _prepare(monkeypatch, tmp_path)
    commands = []

    def runner(command, **kwargs):
        action = command[-1]
        commands.append(action)
        if action == "up" and commands.count("up") == 1:
            return subprocess.CompletedProcess(command, 9)
        return _completed(command)

    def mutating_probe(*args, **kwargs):
        replacement = tmp_path / "late-source-replacement"
        replacement.write_bytes(env.read_bytes())
        os.replace(replacement, env)
        return type("Probe", (), {"ok": True, "detail": "local setup"})()

    monkeypatch.setattr(
        "skeleton.app.health.probe_local_setup", mutating_probe,
    )
    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=runner,
    )
    assert receipt.ok is False
    assert commands == ["config", "up", "up"]
    assert receipt.phases[-1].name == "runtime-source-epoch"
    assert not any(p.name == "setup-ui-availability" for p in receipt.phases)


def test_stable_setup_ui_recovery_does_not_promote_protected_stack(
    tmp_path, monkeypatch,
):
    _prepare(monkeypatch, tmp_path)
    commands = []

    def runner(command, **kwargs):
        action = command[-1]
        commands.append(action)
        if action == "up" and commands.count("up") == 1:
            return subprocess.CompletedProcess(command, 9)
        return _completed(command)

    monkeypatch.setattr(
        "skeleton.app.health.probe_local_setup",
        lambda *args, **kwargs: type(
            "Probe", (), {"ok": True, "detail": "local setup available"},
        )(),
    )
    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=runner,
    )
    assert commands == ["config", "up", "up"]
    assert receipt.ok is False
    assert any(p.name == "setup-ui-availability" and p.ok for p in receipt.phases)
    assert any(p.name == "start" and not p.ok and p.required for p in receipt.phases)


def test_runtime_fingerprint_rejects_inplace_rewrite_during_bounded_read(
    tmp_path, monkeypatch,
):
    from skeleton.app import setup_runtime

    env = tmp_path / ".env"
    env.write_text("JWT_SECRET=local-fixture\n", encoding="utf-8")
    original_reader = setup_runtime._read_existing_env

    def changing_reader(path, **kwargs):
        contents, repaired = original_reader(path, **kwargs)
        before = path.stat()
        os.utime(path, ns=(
            before.st_atime_ns, before.st_mtime_ns + 2_000_000_000,
        ))
        return contents, repaired

    monkeypatch.setattr(setup_runtime, "_read_existing_env", changing_reader)
    with pytest.raises(ValueError, match="runtime configuration source"):
        runtime_source_fingerprint(tmp_path)


def test_installer_binds_frontend_probe_to_admitted_environment(
    tmp_path, monkeypatch,
):
    _prepare(monkeypatch, tmp_path)
    monkeypatch.setenv("FRONTEND_PORT", "3100")
    from skeleton.app.health import ProbeResult

    observed = []
    commands = []

    def runner(command, **kwargs):
        commands.append((command[-1], kwargs.get("env", {}).get("FRONTEND_PORT")))
        if command[-1] == "config":
            monkeypatch.setenv("FRONTEND_PORT", "3300")
        return _completed(command)

    def wait_for_health(**kwargs):
        observed.append(dict(kwargs["public_url_overrides"]))
        return (ProbeResult(
            "backend", "http://localhost:8001", True, 200, "healthy",
        ),)

    monkeypatch.setattr("skeleton.app.health.wait_for_application", wait_for_health)
    monkeypatch.setattr(
        "skeleton.app.first_install.critical_backend_route_report",
        lambda *args, **kwargs: {"ready": True},
    )
    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=runner,
    )
    assert receipt.ok, receipt.to_dict()
    assert commands == [("config", "3100"), ("up", "3100")]
    assert observed == [{
        "frontend": "http://localhost:3100",
        "backend": "http://localhost:8001",
    }]
    assert os.environ["FRONTEND_PORT"] == "3300"


def test_install_manifest_resolution_cannot_change_later_probe_epoch(
    tmp_path, monkeypatch,
):
    _prepare(monkeypatch, tmp_path)
    monkeypatch.setenv("FRONTEND_PORT", "3100")
    resolved = installer.runtime_manifest
    observed = []

    def changing_manifest(*args, **kwargs):
        manifest = resolved(*args, **kwargs)
        monkeypatch.setenv("FRONTEND_PORT", "3300")
        return manifest

    monkeypatch.setattr(installer, "runtime_manifest", changing_manifest)
    from skeleton.app.health import ProbeResult

    def wait_for_health(**kwargs):
        observed.append(kwargs["public_url_overrides"].get("frontend"))
        return (ProbeResult(
            "backend", "http://localhost:8001", True, 200, "healthy",
        ),)

    monkeypatch.setattr("skeleton.app.health.wait_for_application", wait_for_health)
    monkeypatch.setattr(
        "skeleton.app.first_install.critical_backend_route_report",
        lambda *args, **kwargs: {"ready": True},
    )
    receipt = installer.install_application(
        tmp_path, start=True, install_python=False,
        runner=lambda command, **kwargs: _completed(command),
    )
    assert receipt.ok, receipt.to_dict()
    assert observed == ["http://localhost:3100"]


def test_preflight_and_startup_share_exact_process_environment(
    tmp_path, monkeypatch,
):
    _prepare(monkeypatch, tmp_path)
    monkeypatch.setenv("FRONTEND_PORT", "3100")
    seen = []
    from skeleton.app.health import ProbeResult

    def mutating_preflight(*args, **kwargs):
        seen.append(("preflight", kwargs["environ"]["FRONTEND_PORT"]))
        monkeypatch.setenv("FRONTEND_PORT", "3300")
        return ()

    monkeypatch.setattr(installer, "preflight", mutating_preflight)

    def runner(command, **kwargs):
        seen.append((command[-1], kwargs["env"]["FRONTEND_PORT"]))
        return _completed(command)

    def probe(**kwargs):
        seen.append(("probe", kwargs["public_url_overrides"]["frontend"]))
        return (ProbeResult(
            "backend", "http://localhost:8001", True, 200, "healthy",
        ),)

    monkeypatch.setattr("skeleton.app.health.wait_for_application", probe)
    monkeypatch.setattr(
        "skeleton.app.first_install.critical_backend_route_report",
        lambda *args, **kwargs: {"ready": True},
    )
    receipt = installer.install_application(
        tmp_path, start=True, install_python=False, runner=runner,
    )
    assert receipt.ok, receipt.to_dict()
    assert seen == [
        ("preflight", "3100"),
        ("config", "3100"),
        ("up", "3100"),
        ("probe", "http://localhost:3100"),
    ]


@pytest.mark.parametrize("same_bytes", [True, False])
def test_runtime_preflight_cannot_swap_private_config_before_epoch_admission(
    tmp_path, monkeypatch, same_bytes,
):
    env = _prepare(monkeypatch, tmp_path)
    _forbid_network(monkeypatch)

    def changing_preflight(*args, **kwargs):
        original = env.read_bytes()
        replacement = tmp_path / "operator-preflight-change"
        replacement.write_bytes(
            original if same_bytes else original + b"PORT_OVERRIDE=untrusted\n"
        )
        os.replace(replacement, env)
        return ()

    monkeypatch.setattr(installer, "preflight", changing_preflight)
    receipt = installer.install_application(
        tmp_path, start=True, install_python=False,
        runner=lambda *args, **kwargs: pytest.fail(
            "preflight source drift must reject before Compose runs"
        ),
    )
    assert receipt.ok is False
    assert receipt.phases[-1].name == "runtime-source-epoch"
    assert not any(x.name in {"compose-config", "start", "readiness"}
                   for x in receipt.phases)
