"""Standard-library offline kit packaging, integrity and no-network installation gating."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

import pytest

from scripts.offline_kit import OfflineKitError, pack, verify, install


def _wheels(tmp_path: Path) -> Path:
    source = tmp_path / "wheels"
    source.mkdir()
    (source / "skeleton-16.0.0-py3-none-any.whl").write_bytes(b"fixture-wheel")
    (source / "example_dep-1.0.0-py3-none-any.whl").write_bytes(b"dependency-wheel")
    return source


def test_pack_and_verify_file_pinned_offline_kit(tmp_path: Path) -> None:
    source = _wheels(tmp_path)
    target = pack(source, tmp_path / "output")
    data = verify(target)
    assert data["version"] == "16.0.0"
    assert data["gguf_included"] is False
    assert (target / "offline_kit.py").is_file()
    assert len(data["files"]) == 3
    assert [item["path"] for item in data["files"]] == sorted(
        item["path"] for item in data["files"]
    )


def test_file_tampering_or_extra_artifact_rejected(tmp_path: Path) -> None:
    target = pack(_wheels(tmp_path), tmp_path / "output")
    wheel = target / "wheelhouse" / "skeleton-16.0.0-py3-none-any.whl"
    wheel.write_bytes(wheel.read_bytes() + b"x")
    with pytest.raises(OfflineKitError, match="pinned manifest"):
        verify(target)
    # Restore the first tamper and add an undeclared file.
    wheel.write_bytes(b"fixture-wheel")
    (target / "wheelhouse" / "unexpected.txt").write_text("untrusted")
    with pytest.raises(OfflineKitError, match="pinned manifest|wheelhouse"):
        verify(target)


def test_symlinked_wheelhouse_input_and_missing_skeleton_rejected(tmp_path: Path) -> None:
    source = _wheels(tmp_path)
    (source / "skeleton-16.0.0-py3-none-any.whl").unlink()
    with pytest.raises(OfflineKitError, match="Skeleton version"):
        pack(source, tmp_path / "output")
    (source / "skeleton-16.0.0-py3-none-any.whl").write_bytes(b"fixture")
    link = source / "other-1.0-py3-none-any.whl"
    try:
        link.symlink_to(source / "skeleton-16.0.0-py3-none-any.whl")
    except OSError:
        pytest.skip("host cannot create symlinks")
    with pytest.raises(OfflineKitError, match="regular"):
        pack(source, tmp_path / "output")


def test_gguf_and_local_executable_are_bundled_and_referenced(tmp_path: Path) -> None:
    source = _wheels(tmp_path)
    gguf = tmp_path / "weights.gguf"
    gguf.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 0) + b"model-fixture")
    runner = tmp_path / "llama-cli"
    runner.write_bytes(b"fixture-executable")
    target = pack(
        source, tmp_path / "output", gguf=gguf, llama=runner, model_id="local-agent",
    )
    data = verify(target)
    assert data["gguf_included"] is True
    deployment = json.loads((target / "model" / "deployment.json").read_text())
    assert deployment["model_id"] == "local-agent"
    assert deployment["model_sha256"] == hashlib.sha256(gguf.read_bytes()).hexdigest()
    assert deployment["executable_path"].startswith("../runtime/")
    assert deployment["model_path"] == "model.gguf"
    model_in_kit = target / "model" / "model.gguf"
    model_in_kit.write_bytes(b"untrusted")
    with pytest.raises(OfflineKitError, match="pinned manifest"):
        verify(target)


def test_gguf_pair_is_required(tmp_path: Path) -> None:
    source = _wheels(tmp_path)
    with pytest.raises(OfflineKitError, match="both required"):
        pack(source, tmp_path / "output", gguf=tmp_path / "missing.gguf")


def test_install_rejects_incompatible_python_before_any_installation(
    tmp_path: Path, monkeypatch
) -> None:
    import scripts.offline_kit as kit
    source = _wheels(tmp_path)
    target = pack(source, tmp_path / "output")
    actual = kit._environment
    monkeypatch.setattr(kit, "_environment", lambda: {**actual(), "python_minor": "0.0"})
    installed = tmp_path / "installed"
    with pytest.raises(OfflineKitError, match="architecture differs"):
        install(target, installed)
    assert not installed.exists()


def test_install_rejects_existing_destination(tmp_path: Path) -> None:
    target = pack(_wheels(tmp_path), tmp_path / "output")
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(OfflineKitError, match="already exists"):
        install(target, existing)


def _fake_installer(monkeypatch, *, fail: bool = False, mutate=None):
    import os
    import subprocess
    import scripts.offline_kit as kit

    class Builder:
        def __init__(self, **kwargs):
            assert kwargs["with_pip"] is True

        def create(self, target):
            root = Path(target)
            interpreter = root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text("installed", encoding="utf-8")

    commands = []

    def fake_run(args, **kwargs):
        commands.append((args, kwargs))
        if mutate is not None:
            mutate()
        if fail:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(kit.venv, "EnvBuilder", Builder)
    monkeypatch.setattr(kit.subprocess, "run", fake_run)
    return commands


def test_successful_offline_install_never_uses_index_and_keeps_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    bundle = pack(_wheels(tmp_path), tmp_path / "output")
    recorded = _fake_installer(monkeypatch)
    target = install(bundle, tmp_path / "installed")
    assert (target / ("Scripts/python.exe" if __import__("os").name == "nt" else "bin/python")).is_file()
    args, kwargs = recorded[0]
    assert "--no-index" in args
    assert "--no-input" in args
    assert "--no-cache-dir" in args
    assert "--only-binary=:all:" in args
    assert "skeleton[local-inference]==16.0.0" in args
    assert kwargs["shell"] is False
    assert kwargs["env"]["PIP_NO_INDEX"] == "1"


def test_pip_failure_removes_new_install_and_preserves_kit(
    tmp_path: Path, monkeypatch
) -> None:
    import subprocess
    bundle = pack(_wheels(tmp_path), tmp_path / "output")
    _fake_installer(monkeypatch, fail=True)
    target = tmp_path / "installed"
    with pytest.raises(subprocess.CalledProcessError):
        install(bundle, target)
    assert not target.exists()
    assert verify(bundle)["version"] == "16.0.0"


def test_kit_mutated_during_install_fails_and_rolls_back(
    tmp_path: Path, monkeypatch
) -> None:
    bundle = pack(_wheels(tmp_path), tmp_path / "output")
    wheel = bundle / "wheelhouse" / "example_dep-1.0.0-py3-none-any.whl"
    _fake_installer(monkeypatch, mutate=lambda: wheel.write_bytes(b"replaced"))
    target = tmp_path / "installed"
    with pytest.raises(OfflineKitError, match="pinned manifest"):
        install(bundle, target)
    assert not target.exists()
