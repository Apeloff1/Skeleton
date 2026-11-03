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
