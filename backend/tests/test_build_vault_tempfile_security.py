from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import build_vault


def _vault_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.setattr(build_vault, "BUILDS_ROOT", root)
    return root


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")


def test_writable_probe_does_not_follow_legacy_fixed_probe_symlink(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("sentinel", encoding="utf-8")
    legacy_probe = tmp_path / ".w_probe"
    _symlink_or_skip(legacy_probe, victim)

    build_vault._probe_writable_dir(tmp_path)

    assert victim.read_text(encoding="utf-8") == "sentinel"
    assert legacy_probe.is_symlink()
    assert list(tmp_path.glob(".w_probe.*")) == []


def test_atomic_writer_does_not_follow_legacy_manifest_temp_symlink(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    victim = tmp_path / "victim.txt"
    victim.write_text("sentinel", encoding="utf-8")
    legacy_tmp = target.with_suffix(".tmp")
    _symlink_or_skip(legacy_tmp, victim)

    build_vault._atomic_write_text(target, '{"ok":true}')

    assert victim.read_text(encoding="utf-8") == "sentinel"
    assert legacy_tmp.is_symlink()
    assert target.read_text(encoding="utf-8") == '{"ok":true}'


def test_atomic_writer_cleans_unique_temp_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "manifest.json"

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr(build_vault.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        build_vault._atomic_write_text(target, "{}")

    assert not target.exists()
    assert list(tmp_path.glob(".manifest.json.*.tmp")) == []


def test_manifest_write_ignores_legacy_predictable_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _vault_root(tmp_path, monkeypatch)
    build_dir = root / "build-1"
    build_dir.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("sentinel", encoding="utf-8")
    legacy_tmp = build_dir / "manifest.tmp"
    _symlink_or_skip(legacy_tmp, victim)

    build_vault._write_manifest("build-1", {"build_id": "build-1", "shards": []})

    assert victim.read_text(encoding="utf-8") == "sentinel"
    assert legacy_tmp.is_symlink()
    manifest = json.loads((build_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["build_id"] == "build-1"


def test_failed_marker_replaces_symlink_instead_of_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _vault_root(tmp_path, monkeypatch)
    build_dir = root / "build-2"
    build_dir.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("sentinel", encoding="utf-8")
    marker = build_dir / "FAILED.marker"
    _symlink_or_skip(marker, victim)

    stats = build_vault.preserve_on_failure("build-2")

    assert victim.read_text(encoding="utf-8") == "sentinel"
    assert marker.is_file()
    assert not marker.is_symlink()
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["build_id"] == "build-2"
    assert stats["build_id"] == "build-2"
