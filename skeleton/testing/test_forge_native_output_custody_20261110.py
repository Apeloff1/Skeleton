"""Forge export custody: bounded output inventory and no-clobber reports.

These tests explicitly avoid launching Godot and do not qualify real boot,
export templates, native binaries or release provenance.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from skeleton.forge import export as forge_export
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.godot_export import provenance


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="requires descriptor-relative POSIX file custody",
)


def test_native_artifact_digest_is_byte_compatible(tmp_path):
    target = tmp_path / "game.pck"
    payload = b"canonical-native-output" * 64
    target.write_bytes(payload)
    assert forge_export._artifact_digest(target) == hashlib.sha256(payload).hexdigest()


def test_native_digest_uses_its_explicit_cap_not_manifest_cap(tmp_path):
    target = tmp_path / "game.pck"
    payload = b"z" * 80
    target.write_bytes(payload)
    with patch.object(forge_export, "MAX_OUTPUT_BYTES", 128):
        with patch.object(provenance, "MAX_ARTIFACT_BYTES", 64):
            assert forge_export._artifact_digest(target) == hashlib.sha256(payload).hexdigest()
        with patch.object(forge_export, "MAX_OUTPUT_BYTES", 70):
            with pytest.raises(ValueError, match="oversized"):
                forge_export._artifact_digest(target)


def test_native_digest_rejects_swapped_ancestor_even_when_bytes_match(tmp_path):
    parent = tmp_path / "output"
    parent.mkdir()
    target = parent / "game.pck"
    payload = b"native" * 2048
    target.write_bytes(payload)
    replacement = tmp_path / "waiting"
    replacement.mkdir()
    (replacement / "game.pck").write_bytes(payload)
    detached = tmp_path / "detached"
    original = os.read
    swapped = False

    def swap_when_read(fd, count):
        nonlocal swapped
        data = original(fd, count)
        if data and not swapped:
            swapped = True
            parent.rename(detached)
            replacement.rename(parent)
        return data

    with patch.object(forge_export.os, "read", side_effect=swap_when_read):
        with pytest.raises(ValueError, match="ancestor path"):
            forge_export._artifact_digest(target)
    assert swapped
    assert (parent / "game.pck").read_bytes() == payload


def test_create_only_report_refuses_clobber(tmp_path):
    path = tmp_path / "reports" / "native.json"
    forge_export._write_report_new(path, '{"status":"NO-SHIP"}')
    first = path.read_bytes()
    with pytest.raises(FileExistsError):
        forge_export._write_report_new(path, '{"status":"SHIP"}')
    assert path.read_bytes() == first
    assert path.stat().st_nlink == 1


def test_report_cannot_follow_existing_symlink(tmp_path):
    secret = tmp_path / "other.json"
    secret.write_text('{"retained":"yes"}', encoding="utf-8")
    alias = tmp_path / "report.json"
    alias.symlink_to(secret)
    with pytest.raises(FileExistsError):
        forge_export._write_report_new(alias, '{"status":"SHIP"}')
    assert secret.read_text(encoding="utf-8") == '{"retained":"yes"}'


def test_report_cannot_follow_intermediate_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        forge_export._write_report_new(alias / "native.json", '{"status":"SHIP"}')
    assert not (outside / "native.json").exists()


def test_report_byte_budget_and_write_failure_cleanup(tmp_path):
    report = tmp_path / "report.json"
    with patch.object(forge_export, "MAX_REPORT_BYTES", 8):
        with pytest.raises(ValueError, match="byte budget"):
            forge_export._write_report_new(report, "X" * 50)
    assert not report.exists()
    with patch.object(forge_export.os, "fsync", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            forge_export._write_report_new(report, "{}")
    assert not report.exists()



def test_report_parent_swap_after_fsync_cannot_publish_receipt(tmp_path):
    import stat

    root = tmp_path / "reports"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    detached = tmp_path / "detached"
    target = root / "run.json"
    original_fsync = os.fsync
    swapped = False

    def swap_after_directory_flush(fd):
        nonlocal swapped
        original_fsync(fd)
        if not swapped and stat.S_ISDIR(os.fstat(fd).st_mode):
            root.rename(detached)
            root.symlink_to(outside, target_is_directory=True)
            swapped = True

    with patch.object(
        forge_export.os, "fsync", side_effect=swap_after_directory_flush,
    ):
        with pytest.raises(ValueError, match="report parent changed"):
            forge_export._write_report_new(target, '{"status":"SHIP"}')
    assert swapped
    assert not (outside / "run.json").exists()
    assert not (detached / "run.json").exists()


def test_report_cleanup_does_not_unlink_competing_entry(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    target = root / "run.json"
    saved = root / "saved.json"
    original = forge_export._verify_report_parent

    def substitute_before_final_check(parent, dfd):
        target.rename(saved)
        target.write_text('{"competitor":"must-survive"}', encoding="utf-8")
        original(parent, dfd)

    with patch.object(
        forge_export, "_verify_report_parent",
        side_effect=substitute_before_final_check,
    ):
        with pytest.raises(ValueError, match="report path changed"):
            forge_export._write_report_new(target, '{"status":"SHIP"}')
    assert target.read_text(encoding="utf-8") == '{"competitor":"must-survive"}'
    assert saved.read_text(encoding="utf-8") == '{"status":"SHIP"}'



def test_report_same_size_tampering_before_readback_fails_closed(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    target = root / "receipt.json"
    original_verify = forge_export._verify_report_parent
    modified = False

    def mutate_after_parent_validation(parent, dfd):
        nonlocal modified
        original_verify(parent, dfd)
        if not modified:
            # Same inode and byte count, but not the bytes the author wrote.
            target.write_bytes(b'{"status":"NO-SHIP"}')
            modified = True

    with patch.object(
        forge_export, "_verify_report_parent",
        side_effect=mutate_after_parent_validation,
    ):
        with pytest.raises(ValueError, match="contents changed"):
            forge_export._write_report_new(target, '{"status":"SUCCESS"}')
    assert modified
    assert not target.exists()


def test_report_revalidates_parent_after_readback(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    target = root / "receipt.json"
    outside = tmp_path / "outside"
    outside.mkdir()
    old = tmp_path / "detached"
    original_verify = forge_export._verify_report_parent
    calls = 0

    def swap_before_second_validation(parent, dfd):
        nonlocal calls
        calls += 1
        if calls == 2:
            root.rename(old)
            root.symlink_to(outside, target_is_directory=True)
        return original_verify(parent, dfd)

    with patch.object(
        forge_export, "_verify_report_parent",
        side_effect=swap_before_second_validation,
    ):
        with pytest.raises(ValueError, match="parent changed"):
            forge_export._write_report_new(target, '{"status":"NO-SHIP"}')
    assert calls == 2
    assert not (outside / "receipt.json").exists()
    assert not (old / "receipt.json").exists()


def test_report_final_component_symlink_swap_cannot_read_other_file(tmp_path):
    target = tmp_path / "receipt.json"
    private = tmp_path / "private.txt"
    private.write_text("sensitive canary", encoding="utf-8")
    saved = tmp_path / "saved.json"
    original_open = os.open
    swapped = False

    def substitute_before_read(file, flags, *args, **kwargs):
        nonlocal swapped
        if (file == target.name and kwargs.get("dir_fd") is not None
                and flags & os.O_RDONLY == os.O_RDONLY
                and not (flags & os.O_WRONLY)
                and not swapped):
            target.rename(saved)
            target.symlink_to(private)
            swapped = True
        return original_open(file, flags, *args, **kwargs)

    # Patching os.open changes its Python object identity. Preserve the
    # descriptor-relative capability advertisement for the fake function;
    # otherwise this regression fails at admission instead of reaching the
    # attacker-controlled O_NOFOLLOW final-component open.
    with patch.object(
        forge_export.os, "open", side_effect=substitute_before_read,
    ) as guarded_open:
        with patch.object(
            forge_export.os, "supports_dir_fd",
            set(os.supports_dir_fd) | {guarded_open},
        ):
            with pytest.raises(OSError):
                forge_export._write_report_new(
                    target, '{"status":"NO-SHIP"}',
                )
    assert swapped
    assert private.read_text(encoding="utf-8") == "sensitive canary"
    assert target.is_symlink()
    assert saved.read_bytes() == b'{"status":"NO-SHIP"}'


def test_native_export_refuses_aggregate_bytes_before_hash_and_boot(
    tmp_path, monkeypatch,
):
    emitted = emit_godot(compile_era("extraction_now"), title="byte-limited")
    monkeypatch.setattr(
        forge_export, "resolve_binary",
        lambda binary=None: ("/bin/true", "mock-only", False),
    )
    monkeypatch.setattr(forge_export, "MAX_EXPORT_TOTAL_BYTES", 12)
    calls = []
    def fake_run(command, cwd, timeout):
        calls.append(command)
        if "--export-release" in command:
            target = Path(command[-1])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"0123456789")
            target.with_suffix(".pck").write_bytes(b"abcdefghij")
        return 0, "", False

    monkeypatch.setattr(forge_export, "_run", fake_run)
    with patch.object(
        forge_export, "_artifact_digest",
        side_effect=AssertionError("must reject before expensive SHA hashing"),
    ), patch.object(
        forge_export, "_boot_exported",
        side_effect=AssertionError("must not boot over-budget image"),
    ):
        report = forge_export.export_build(
            emitted, tmp_path / "native", presets=("Linux",),
        )
    assert report["passed"] is False
    assert report["release_certified"] is False
    assert report["reason"] == "output-byte-budget"
    assert report["presets"]["Linux"]["bytes"] == 20
    assert report["presets"]["Linux"]["reason"] == (
        "cumulative-output-byte-budget-exceeded"
    )
    assert len([call for call in calls if "--export-release" in call]) == 1


def test_cumulative_budget_covers_all_requested_presets(tmp_path, monkeypatch):
    emitted = emit_godot(compile_era("extraction_now"), title="multi-preset")
    monkeypatch.setattr(
        forge_export, "resolve_binary",
        lambda binary=None: ("/bin/true", "mock-only", False),
    )
    monkeypatch.setattr(forge_export, "MAX_EXPORT_TOTAL_BYTES", 24)
    def fake_run(command, cwd, timeout):
        if "--export-release" in command:
            target = Path(command[-1])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"12345678")
            required = ".pck" if "game.x86_64" in target.name else ".wasm"
            target.with_suffix(required).write_bytes(b"abcdefgh")
        return 0, "", False

    monkeypatch.setattr(forge_export, "_run", fake_run)
    monkeypatch.setattr(
        forge_export, "_boot_exported",
        lambda executable, frames, timeout: {"passed": True},
    )
    report = forge_export.export_build(
        emitted, tmp_path / "native", presets=("Linux", "Web"),
    )
    assert report["passed"] is False
    assert report["release_certified"] is False
    assert report["presets"]["Linux"]["ok"] is True
    assert report["presets"]["Web"]["ok"] is False
    assert report["presets"]["Web"]["reason"] == (
        "cumulative-output-byte-budget-exceeded"
    )


def test_native_output_inventory_stops_at_file_cap(tmp_path, monkeypatch):
    """A fake runner creates too many files; no real Godot invocation occurs."""
    emitted = emit_godot(compile_era("extraction_now"), title="bounded-export")
    monkeypatch.setattr(
        forge_export, "resolve_binary",
        lambda binary=None: ("/bin/true", "test-only", False),
    )
    exported = False

    def fake_run(command, cwd, timeout):
        nonlocal exported
        if "--export-release" in command:
            exported = True
            target = Path(command[-1])
            target.parent.mkdir(parents=True, exist_ok=True)
            for index in range(forge_export.MAX_OUTPUT_FILES + 1):
                (target.parent / f"output-{index}.bin").write_bytes(b"fixture")
        return 0, "", False

    monkeypatch.setattr(forge_export, "_run", fake_run)
    result = forge_export.export_build(
        emitted, tmp_path / "native", presets=("Linux",),
    )
    assert exported
    assert result["passed"] is False
    assert result["release_certified"] is False
    entry = result["presets"]["Linux"]
    assert entry["ok"] is False
    assert entry["reason"] == "unsafe-or-unbounded-artifacts"
    assert entry["artefacts"] == []
