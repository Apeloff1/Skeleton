"""Cross-process installer secret custody and hostile setup input regressions.

These are focused source tests, not Windows 11, WSL2, Docker or AI qualification.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import time

import pytest

from skeleton.app.setup_runtime import (
    _MAX_ENV_BYTES,
    _setup_process_lock,
    _prepare_model_directory,
    ensure_runtime_environment,
)


def _root(tmp_path: Path) -> Path:
    (tmp_path / ".env.example").write_text(
        "MONGO_INITDB_ROOT_USERNAME=admin\n"
        "MONGO_INITDB_ROOT_PASSWORD=\n"
        "JWT_SECRET=\n"
        "AI_PROVIDER=local\n",
        encoding="utf-8",
    )
    return tmp_path


def _keys(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def test_setup_generates_stable_cross_process_secrets(tmp_path):
    root = _root(tmp_path)
    first = ensure_runtime_environment(root)
    initial = _keys(root / ".env")
    assert first.created and first.changed
    assert initial["SKL_ENGINE_SERVICE_TOKEN"]
    assert initial["SKELETON_MASTER_SECRET"]
    assert initial["GF_KEYHOLDER_SEED"]
    assert initial["JWT_SECRET"]
    assert initial["AI_PROVIDER"] == "local"
    second = ensure_runtime_environment(root)
    assert not second.changed
    assert _keys(root / ".env") == initial
    assert (root / ".skeleton-setup.lock").is_file()
    if os.name != "nt":
        assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o600
        assert stat.S_IMODE((root / ".skeleton-setup.lock").stat().st_mode) == 0o600
    assert not list(root.glob(".env.*.tmp"))


def test_setup_rejects_linked_env_without_touching_target(tmp_path):
    root = _root(tmp_path)
    target = tmp_path / "private-target"
    target.write_text("DO_NOT_CHANGE\n", encoding="utf-8")
    try:
        (root / ".env").symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation unavailable on this host")
    with pytest.raises(ValueError, match="symbolic link"):
        ensure_runtime_environment(root)
    assert target.read_text(encoding="utf-8") == "DO_NOT_CHANGE\n"


def test_setup_rejects_oversized_env_before_secret_generation(tmp_path):
    root = _root(tmp_path)
    (root / ".env").write_bytes(b"X" * (_MAX_ENV_BYTES + 1))
    with pytest.raises(ValueError, match="256 KiB"):
        ensure_runtime_environment(root)
    assert (root / ".env").stat().st_size == _MAX_ENV_BYTES + 1


def test_setup_rejects_linked_lock_path(tmp_path):
    root = _root(tmp_path)
    target = root / "lock-target"
    target.write_text("untouched", encoding="utf-8")
    try:
        (root / ".skeleton-setup.lock").symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation unavailable on this host")
    with pytest.raises(ValueError, match="symbolic link"):
        ensure_runtime_environment(root)
    assert target.read_text(encoding="utf-8") == "untouched"


def test_independent_process_cannot_interleave_bootstrap(tmp_path):
    root = _root(tmp_path)
    marker = root / "lock-acquired"
    script = "\n".join(
        [
            "import sys, time",
            "from pathlib import Path",
            "from skeleton.app.setup_runtime import _setup_process_lock",
            "root = Path(sys.argv[1])",
            "marker = Path(sys.argv[2])",
            "with _setup_process_lock(root):",
            "    marker.write_text('ready', encoding='utf-8')",
            "    time.sleep(1.2)",
            "",
        ]
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(root), str(marker)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 8
        while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.03)
        if not marker.exists():
            _, stderr = child.communicate(timeout=2)
            pytest.fail("child failed to acquire setup lock: " + stderr.decode(errors="replace")[-500:])
        with pytest.raises(TimeoutError, match="another setup process"):
            with _setup_process_lock(root, timeout=0.15):
                pytest.fail("concurrent process acquired held setup lock")
        assert child.wait(timeout=5) == 0
        with _setup_process_lock(root, timeout=1):
            assert (root / ".skeleton-setup.lock").is_file()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_two_independent_installers_publish_one_shared_secret_epoch(tmp_path):
    """Competing first-run processes must not each initialize different keys."""
    import json

    root = _root(tmp_path)
    gate = root / "begin-bootstrap"
    markers = [root / "worker-one-ready", root / "worker-two-ready"]
    script = "\n".join(
        [
            "import json, sys, time",
            "from pathlib import Path",
            "from skeleton.app.setup_runtime import ensure_runtime_environment",
            "root, marker, gate = map(Path, sys.argv[1:4])",
            "marker.write_text('ready', encoding='utf-8')",
            "deadline = time.monotonic() + 8",
            "while not gate.exists() and time.monotonic() < deadline:",
            "    time.sleep(0.01)",
            "if not gate.exists(): sys.exit(7)",
            "result = ensure_runtime_environment(root)",
            "print(json.dumps({'created': result.created, 'changed': result.changed}))",
            "",
        ]
    )
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(root), str(marker), str(gate)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for marker in markers
    ]
    try:
        deadline = time.monotonic() + 8
        while not all(marker.exists() for marker in markers) and time.monotonic() < deadline:
            if any(worker.poll() is not None for worker in workers):
                break
            time.sleep(0.02)
        assert all(marker.exists() for marker in markers), "workers did not reach the admission barrier"
        gate.write_text("begin", encoding="utf-8")
        results = []
        for worker in workers:
            stdout, stderr = worker.communicate(timeout=20)
            assert worker.returncode == 0, f"worker exited {worker.returncode}: {stderr[-300:]}"
            results.append(json.loads(stdout))
        assert sorted(result["created"] for result in results) == [False, True]
        assert sorted(result["changed"] for result in results) == [False, True]
        values = _keys(root / ".env")
        assert values["SKL_ENGINE_SERVICE_TOKEN"]
        assert values["GF_KEYHOLDER_SEED"]
        assert not ensure_runtime_environment(root).changed
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)


def test_installer_fails_closed_and_redacts_lock_timeout(tmp_path, monkeypatch):
    from skeleton.app.installer import install_application
    from skeleton.app.preloader import PreloadReport

    root = _root(tmp_path)
    monkeypatch.setattr(
        "skeleton.app.installer.inspect_host",
        lambda *args, **kwargs: PreloadReport(root=root, platform="test", python=sys.executable, checks=()),
    )

    def unavailable(*args, **kwargs):
        raise TimeoutError("private operator secret from blocked bootstrap")

    def forbidden(*args, **kwargs):
        pytest.fail("failed setup must not start installation subprocesses")

    monkeypatch.setattr("skeleton.app.installer.ensure_runtime_environment", unavailable)
    receipt = install_application(root, install_python=False, runner=forbidden)
    assert not receipt.ok
    assert receipt.phases[-1].name == "setup-runtime"
    assert "TimeoutError" in receipt.phases[-1].detail
    assert "private operator secret" not in repr(receipt.to_dict())
    assert not (root / ".env").exists()


def test_existing_env_fifo_fails_without_waiting_for_a_writer(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO support unavailable")
    root = _root(tmp_path)
    os.mkfifo(root / ".env")
    before = time.monotonic()
    with pytest.raises(ValueError, match="stable, unaliased regular file"):
        ensure_runtime_environment(root)
    assert time.monotonic() - before < 2.0
    assert not list(root.glob(".env.*.tmp"))


def test_existing_env_hardlink_alias_is_rejected_without_mutation(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX inode-link custody contract")
    root = _root(tmp_path)
    target = root / "outside-env-alias"
    target.write_text("JWT_SECRET=original\\n", encoding="utf-8")
    os.link(target, root / ".env")
    with pytest.raises(ValueError, match="unaliased regular file"):
        ensure_runtime_environment(root)
    assert target.read_text(encoding="utf-8") == "JWT_SECRET=original\\n"


def test_example_template_fifo_fails_without_read_or_publication(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO support unavailable")
    root = tmp_path
    os.mkfifo(root / ".env.example")
    before = time.monotonic()
    with pytest.raises(ValueError, match="stable, unaliased regular file"):
        ensure_runtime_environment(root)
    assert time.monotonic() - before < 2.0
    assert not (root / ".env").exists()


def test_example_template_symlink_cannot_import_external_secrets(tmp_path):
    root = tmp_path
    target = root / "external-secrets"
    target.write_text("JWT_SECRET=private-value\\n", encoding="utf-8")
    try:
        (root / ".env.example").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="symbolic link"):
        ensure_runtime_environment(root)
    assert target.read_text(encoding="utf-8") == "JWT_SECRET=private-value\\n"
    assert not (root / ".env").exists()


def test_example_template_oversize_is_bounded_before_secret_generation(tmp_path):
    root = tmp_path
    (root / ".env.example").write_bytes(b"A" * (_MAX_ENV_BYTES + 1))
    with pytest.raises(ValueError, match="256 KiB"):
        ensure_runtime_environment(root)
    assert not (root / ".env").exists()


def test_existing_env_permission_repair_is_private_and_idempotent(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX mode bits are not Windows ACL evidence")
    root = _root(tmp_path)
    ensure_runtime_environment(root)
    path = root / ".env"
    original = path.read_bytes()
    path.chmod(0o644)
    second = ensure_runtime_environment(root)
    assert second.changed and not second.created
    assert not second.configured_keys
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_bytes() == original
    assert any("permissions tightened" in note for note in second.warnings)
    third = ensure_runtime_environment(root)
    assert not third.changed
    assert path.read_bytes() == original


def test_existing_env_private_mode_failure_blocks_bootstrap(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX descriptor permission boundary")
    root = _root(tmp_path)
    ensure_runtime_environment(root)
    path = root / ".env"
    path.chmod(0o644)
    original = path.read_bytes()
    original_fchmod = os.fchmod
    target_inode = path.stat().st_ino
    def blocked(descriptor, mode):
        if os.fstat(descriptor).st_ino == target_inode:
            raise PermissionError("cannot tighten mode")
        return original_fchmod(descriptor, mode)
    monkeypatch.setattr(os, "fchmod", blocked)
    with pytest.raises(PermissionError, match="cannot tighten mode"):
        ensure_runtime_environment(root)
    assert path.read_bytes() == original
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_setup_lock_fifo_is_rejected_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO support unavailable")
    root = _root(tmp_path)
    os.mkfifo(root / ".skeleton-setup.lock")
    before = time.monotonic()
    with pytest.raises(ValueError, match="stable regular file"):
        ensure_runtime_environment(root)
    assert time.monotonic() - before < 2.0
    assert not (root / ".env").exists()


def test_admin_password_fifo_fails_without_waiting_for_writer(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO support unavailable")
    root = _root(tmp_path)
    password = root / "operator-password"
    os.mkfifo(password)
    before = time.monotonic()
    with pytest.raises(ValueError, match="single-link regular file"):
        ensure_runtime_environment(
            root, admin_email="admin@example.test", admin_password_file=password
        )
    assert time.monotonic() - before < 2.0
    assert not (root / ".env").exists()


def test_admin_password_hardlink_alias_is_rejected(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX single-link custody boundary")
    root = _root(tmp_path)
    original = root / "operator-password-original"
    original.write_text("strong-password-value-1234", encoding="utf-8")
    original.chmod(0o600)
    alias = root / "operator-password-alias"
    os.link(original, alias)
    with pytest.raises(ValueError, match="single-link regular file"):
        ensure_runtime_environment(
            root, admin_email="admin@example.test", admin_password_file=alias
        )
    assert original.read_text(encoding="utf-8") == "strong-password-value-1234"
    assert not (root / ".env").exists()


def test_model_mount_preserves_existing_private_mode_and_contents(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX permission preservation is not Windows ACL qualification")
    root = _root(tmp_path)
    mount = root / "private-models"
    mount.mkdir(mode=0o700)
    mount.chmod(0o700)
    marker = mount / "private-weight.bin"
    marker.write_bytes(b"private-model-bytes")
    monkeypatch.setenv("SKELETON_LOCAL_MODEL_DIR", str(mount))
    assert _prepare_model_directory(root, {}) is False
    assert stat.S_IMODE(mount.stat().st_mode) == 0o700
    assert marker.read_bytes() == b"private-model-bytes"
    ensure_runtime_environment(root)
    assert stat.S_IMODE(mount.stat().st_mode) == 0o700
    assert marker.read_bytes() == b"private-model-bytes"


def test_model_mount_new_directory_is_only_reported_once(tmp_path, monkeypatch):
    root = _root(tmp_path)
    mount = root / "new-models"
    monkeypatch.setenv("SKELETON_LOCAL_MODEL_DIR", str(mount))
    assert _prepare_model_directory(root, {}) is True
    assert mount.is_dir()
    assert _prepare_model_directory(root, {}) is False


def test_model_mount_symlink_cannot_chmod_target(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX symlink and mode custody contract")
    root = _root(tmp_path)
    target = root / "private-target-models"
    target.mkdir(mode=0o700)
    target.chmod(0o700)
    link = root / "linked-models"
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("SKELETON_LOCAL_MODEL_DIR", str(link))
    with pytest.raises(ValueError, match="real directory"):
        _prepare_model_directory(root, {})
    assert stat.S_IMODE(target.stat().st_mode) == 0o700


def test_setup_lock_hardlink_alias_rejected_before_chmod(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX hardlink custody contract")
    root = _root(tmp_path)
    target = root / "external-lock-alias"
    target.write_bytes(b"external-lock-unchanged")
    target.chmod(0o644)
    os.link(target, root / ".skeleton-setup.lock")
    original = target.read_bytes()
    with pytest.raises(ValueError, match="stable regular file"):
        ensure_runtime_environment(root)
    assert target.read_bytes() == original
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
    assert not (root / ".env").exists()


def test_admin_password_symlink_rejected_without_secret_import(tmp_path):
    root = _root(tmp_path)
    target = root / "operator-secret-target"
    target.write_text("strong-password-value-1234", encoding="utf-8")
    if os.name != "nt":
        target.chmod(0o600)
    alias = root / "operator-secret-link"
    try:
        alias.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="symbolic link"):
        ensure_runtime_environment(
            root, admin_email="admin@example.test", admin_password_file=alias
        )
    assert target.read_text(encoding="utf-8") == "strong-password-value-1234"
    assert not (root / ".env").exists()


def test_admin_password_path_swap_rejected_before_read(tmp_path, monkeypatch):
    root = _root(tmp_path)
    password = root / "operator-secret"
    password.write_text("strong-password-value-1234", encoding="utf-8")
    if os.name != "nt":
        password.chmod(0o600)
    replacement = root / "operator-secret-replacement"
    replacement.write_text("another-strong-password-1234", encoding="utf-8")
    if os.name != "nt":
        replacement.chmod(0o600)
    original_lstat = os.lstat

    def swap_on_lstat(path, *args, **kwargs):
        if Path(path) == password:
            os.replace(replacement, password)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", swap_on_lstat)
    with pytest.raises(ValueError, match="stable single-link regular file"):
        ensure_runtime_environment(
            root, admin_email="admin@example.test", admin_password_file=password
        )
    assert not (root / ".env").exists()


def test_existing_env_path_swap_during_read_is_rejected(tmp_path, monkeypatch):
    """A validated descriptor cannot authorize a different published pathname."""
    root = _root(tmp_path)
    ensure_runtime_environment(root)
    env = root / ".env"
    replacement = root / "replacement-env"
    replacement.write_bytes(env.read_bytes())
    if os.name != "nt":
        replacement.chmod(0o600)
    original_lstat = os.lstat
    visits = 0

    def swap_after_admission(path, *args, **kwargs):
        nonlocal visits
        if Path(path) == env:
            visits += 1
            if visits == 4:
                os.replace(replacement, env)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", swap_after_admission)
    with pytest.raises(ValueError, match="identity changed during read"):
        ensure_runtime_environment(root)
    assert not list(root.glob(".env.*.tmp"))


def test_admin_password_path_swap_during_read_is_rejected(tmp_path, monkeypatch):
    """Do not accept an orphaned password inode after a successful first admission."""
    root = _root(tmp_path)
    password = root / "operator-secret"
    password.write_text("strong-password-value-1234", encoding="utf-8")
    replacement = root / "replacement-secret"
    replacement.write_text("another-strong-password-1234", encoding="utf-8")
    if os.name != "nt":
        password.chmod(0o600)
        replacement.chmod(0o600)
    original_lstat = os.lstat
    visits = 0

    def swap_after_admission(path, *args, **kwargs):
        nonlocal visits
        if Path(path) == password:
            visits += 1
            if visits == 3:
                os.replace(replacement, password)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", swap_after_admission)
    with pytest.raises(ValueError, match="identity changed during read"):
        ensure_runtime_environment(root, admin_email="admin@example.test", admin_password_file=password)
    assert not (root / ".env").exists()
