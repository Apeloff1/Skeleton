"""The offline installer must feed pip only independently pinned private wheel bytes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import offline_kit


def _kit(tmp_path: Path) -> tuple[Path, dict[str, object], Path]:
    root = tmp_path / "kit"
    wheels = root / "wheelhouse"
    wheels.mkdir(parents=True)
    wheel = wheels / "skeleton-1.0-py3-none-any.whl"
    wheel.write_bytes(b"original pinned wheel bytes")
    payload = wheel.read_bytes()
    manifest = {
        "version": "1.0",
        "environment": offline_kit._environment(),
        "gguf_included": False,
        "files": [{
            "path": "wheelhouse/" + wheel.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }],
    }
    return root, manifest, wheel


def test_private_snapshot_preserves_exact_pinned_wheel_bytes(tmp_path):
    root, manifest, wheel = _kit(tmp_path)
    snapshot = tmp_path / "private" / "wheelhouse"
    snapshot.parent.mkdir()
    offline_kit._snapshot_wheels(root, manifest, snapshot)
    assert (snapshot / wheel.name).read_bytes() == wheel.read_bytes()
    assert snapshot.stat().st_mode & 0o077 == 0


def test_private_snapshot_rejects_changed_and_unlisted_wheels(tmp_path):
    root, manifest, wheel = _kit(tmp_path)
    wheel.write_bytes(b"modified wheel contents")
    with pytest.raises(offline_kit.OfflineKitError, match="digest|changed"):
        offline_kit._snapshot_wheels(root, manifest, tmp_path / "first")
    wheel.write_bytes(b"original pinned wheel bytes")
    (wheel.parent / "other-1.0-py3-none-any.whl").write_bytes(b"unexpected")
    with pytest.raises(offline_kit.OfflineKitError, match="differs"):
        offline_kit._snapshot_wheels(root, manifest, tmp_path / "second")


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow and hardlink contract")
def test_private_snapshot_rejects_symlink_and_hardlink_wheels(tmp_path):
    root, manifest, wheel = _kit(tmp_path)
    original = tmp_path / "outside.whl"
    original.write_bytes(wheel.read_bytes())
    wheel.unlink()
    wheel.symlink_to(original)
    with pytest.raises(offline_kit.OfflineKitError):
        offline_kit._snapshot_wheels(root, manifest, tmp_path / "link")
    wheel.unlink()
    os.link(original, wheel)
    with pytest.raises(offline_kit.OfflineKitError, match="unsafe"):
        offline_kit._snapshot_wheels(root, manifest, tmp_path / "hardlink")


def test_installer_resolves_only_private_snapshot_not_original_kit(tmp_path, monkeypatch):
    root, manifest, wheel = _kit(tmp_path)
    target = tmp_path / "installed"
    seen = []

    monkeypatch.setattr(offline_kit, "verify", lambda _: manifest)

    def fake_create(self, destination):
        executable = Path(destination) / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"test python")

    def fake_run(command, **kwargs):
        assert kwargs["shell"] is False
        assert "--no-index" in command and "--isolated" in command
        directory = Path(command[command.index("--find-links") + 1])
        assert directory != wheel.parent
        wheel.write_bytes(b"attacker-modified original while pip is running")
        assert (directory / wheel.name).read_bytes() == b"original pinned wheel bytes"
        seen.append(directory)
        return None

    monkeypatch.setattr(offline_kit.venv.EnvBuilder, "create", fake_create)
    monkeypatch.setattr(offline_kit.subprocess, "run", fake_run)
    assert offline_kit.install(root, target) == target
    assert len(seen) == 1
    assert not seen[0].exists()
    assert target.is_dir()


def test_install_rejects_copied_model_tampering_and_rolls_back(tmp_path, monkeypatch):
    root, manifest, wheel = _kit(tmp_path)
    model = root / "model"
    runtime = root / "runtime"
    model.mkdir()
    runtime.mkdir()
    runtime_name = "llama-cli.exe" if os.name == "nt" else "llama-cli"
    (model / "model.gguf").write_bytes(b"original local model")
    (runtime / runtime_name).write_bytes(b"original native runtime")
    deployment = {
        "schema_version": "skeleton.local_model.deployment.v1",
        "runtime_kind": "llama.cpp-cli",
        "model_path": "model.gguf",
        "executable_path": "../runtime/" + runtime_name,
        "model_sha256": hashlib.sha256((model / "model.gguf").read_bytes()).hexdigest(),
        "executable_sha256": hashlib.sha256((runtime / runtime_name).read_bytes()).hexdigest(),
    }
    (model / "deployment.json").write_text(json.dumps(deployment))
    manifest["gguf_included"] = True
    for relative in ("model/deployment.json", "model/model.gguf", "runtime/" + runtime_name):
        data = (root / relative).read_bytes()
        manifest["files"].append({
            "path": relative,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        })
    monkeypatch.setattr(offline_kit, "verify", lambda _: manifest)

    def fake_create(self, destination):
        executable = Path(destination) / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"test python")

    monkeypatch.setattr(offline_kit.venv.EnvBuilder, "create", fake_create)
    monkeypatch.setattr(offline_kit.subprocess, "run", lambda *args, **kwargs: None)
    original_copytree = offline_kit.shutil.copytree

    def tamper_copytree(source, destination, **kwargs):
        copied = original_copytree(source, destination, **kwargs)
        if Path(source).name == "model":
            (Path(destination) / "model.gguf").write_bytes(b"attacker-replaced")
        return copied

    monkeypatch.setattr(offline_kit.shutil, "copytree", tamper_copytree)
    target = tmp_path / "installed"
    with pytest.raises(offline_kit.OfflineKitError, match="pinned manifest"):
        offline_kit.install(root, target)
    assert not target.exists()



@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor traversal")
def test_snapshot_rejects_symlinked_kit_parent(tmp_path):
    root, manifest, _ = _kit(tmp_path)
    actual = tmp_path / "actual-kit"
    root.rename(actual)
    root.symlink_to(actual, target_is_directory=True)
    with pytest.raises(offline_kit.OfflineKitError, match="unable to create"):
        offline_kit._snapshot_wheels(root, manifest, tmp_path / "snapshot")
    assert not (tmp_path / "snapshot").exists()


def test_snapshot_directory_flood_rejected_without_private_output(tmp_path):
    root, manifest, _ = _kit(tmp_path)
    for index in range(128):
        (root / "wheelhouse" / f"unlisted-{index:04d}.whl").write_bytes(b"x")
    snapshot = tmp_path / "snapshot"
    with pytest.raises(offline_kit.OfflineKitError, match="differs"):
        offline_kit._snapshot_wheels(root, manifest, snapshot)
    assert not snapshot.exists()



def test_kit_inventory_bounded_before_untrusted_tree_is_materialized(tmp_path, monkeypatch):
    root, _, _ = _kit(tmp_path)
    monkeypatch.setattr(offline_kit, "MAX_FILES", 4)
    for index in range(12):
        (root / f"extra-{index:04d}").write_bytes(b"x")
    with pytest.raises(offline_kit.OfflineKitError, match="entry budget"):
        offline_kit._files(root)


def test_kit_inventory_keeps_canonical_sorted_manifest_order(tmp_path):
    root, _, wheel = _kit(tmp_path)
    (root / "offline_kit.py").write_bytes(b"bootstrap")
    inventory = offline_kit._files(root)
    assert [entry["path"] for entry in inventory] == sorted(
        entry["path"] for entry in inventory
    )
    assert next(entry for entry in inventory if entry["path"].endswith(".whl"))[
        "sha256"
    ] == hashlib.sha256(wheel.read_bytes()).hexdigest()


def _verifiable_kit(tmp_path: Path) -> tuple[Path, dict[str, object], Path]:
    root, manifest, wheel = _kit(tmp_path)
    (root / "offline_kit.py").write_text("# independent bootstrap fixture\\n")
    manifest.update({
        "schema_version": offline_kit.SCHEMA,
        "distribution": "skeleton",
        "files": offline_kit._files(root),
    })
    (root / "manifest.json").write_bytes(offline_kit._canonical(manifest) + b"\\n")
    return root, manifest, wheel


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored POSIX verification")
def test_verify_rejects_symlinked_root_and_ancestor(tmp_path):
    root, manifest, _ = _verifiable_kit(tmp_path)
    assert offline_kit.verify(root) == manifest
    original = tmp_path / "real-kit"
    root.rename(original)
    root.symlink_to(original, target_is_directory=True)
    with pytest.raises(offline_kit.OfflineKitError, match="unsafe|inaccessible"):
        offline_kit.verify(root)
    root.unlink()
    parent = tmp_path / "parent"
    parent.mkdir()
    original.rename(parent / "kit")
    (tmp_path / "alias").symlink_to(parent, target_is_directory=True)
    with pytest.raises(offline_kit.OfflineKitError, match="unsafe|inaccessible"):
        offline_kit.verify(tmp_path / "alias" / "kit")


@pytest.mark.skipif(os.name != "posix", reason="POSIX hardlink identity contract")
def test_verify_rejects_hardlinked_wheel_even_when_digest_matches(tmp_path):
    root, _, wheel = _verifiable_kit(tmp_path)
    os.link(wheel, tmp_path / "outside.whl")
    with pytest.raises(offline_kit.OfflineKitError, match="linked"):
        offline_kit.verify(root)


def test_verify_rejects_ambiguous_duplicate_manifest_keys(tmp_path):
    root, _, _ = _verifiable_kit(tmp_path)
    path = root / "manifest.json"
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b'"distribution":', b'"distribution":"foreign","distribution":', 1))
    with pytest.raises(offline_kit.OfflineKitError, match="duplicate"):
        offline_kit.verify(root)


@pytest.mark.skipif(os.name != "posix", reason="POSIX bounded descriptor inventory")
def test_verify_rejects_directory_flood_before_hashing_unbounded_tree(tmp_path, monkeypatch):
    root, _, _ = _verifiable_kit(tmp_path)
    monkeypatch.setattr(offline_kit, "MAX_FILES", 2)
    for index in range(16):
        (root / f"unlisted-{index:03d}").write_bytes(b"extra")
    with pytest.raises(offline_kit.OfflineKitError, match="entry budget"):
        offline_kit.verify(root)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor pinning")
def test_verify_survives_kit_path_replacement_after_root_descriptor_is_open(tmp_path, monkeypatch):
    root, manifest, _ = _verifiable_kit(tmp_path)
    original_open = offline_kit._open_directory_without_symlink_parents

    def rename_after_open(path):
        descriptor = original_open(path)
        root.rename(tmp_path / "original-moved")
        root.mkdir()
        (root / "manifest.json").write_text("{}", encoding="utf-8")
        return descriptor

    monkeypatch.setattr(offline_kit, "_open_directory_without_symlink_parents",
                        rename_after_open)
    assert offline_kit.verify(root) == manifest


def test_verify_rejects_nonwheel_payload_inside_wheelhouse(tmp_path):
    root, manifest, _ = _verifiable_kit(tmp_path)
    bad = root / "wheelhouse" / "arbitrary.txt"
    bad.write_bytes(b"unexpected")
    manifest["files"] = offline_kit._files(root)
    (root / "manifest.json").write_bytes(offline_kit._canonical(manifest) + b"\\n")
    with pytest.raises(offline_kit.OfflineKitError, match="wheelhouse"):
        offline_kit.verify(root)
