"""Real export receipt integrity around the bounded Godot boot subprocess.

Only ephemeral files are created; the engine itself is not required. No
mocked proof may set the separate release/device certification flags.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from skeleton.forge import export as ex
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="needs descriptor-relative POSIX export custody",
)


def executable(tmp_path: Path) -> Path:
    file = tmp_path / "game.x86_64"
    file.write_bytes(b"\x7fELF" + b"safe-output" * 2048)
    return file


def test_unchanged_binary_boot_receipt_is_source_scoped(tmp_path, monkeypatch):
    exe = executable(tmp_path)
    monkeypatch.setattr(ex, "_run", lambda cmd, cwd, timeout: (0, "", False))
    report = ex._boot_exported(exe, frames=10, timeout=10)
    assert report["passed"] is True
    assert report["errors"] == []


def test_binary_rewritten_during_boot_does_not_pass(tmp_path, monkeypatch):
    exe = executable(tmp_path)

    def rewrite(command, cwd, timeout):
        exe.write_bytes(b"\x7fELF" + b"bad-output!" * 2048)
        return 0, "", False

    monkeypatch.setattr(ex, "_run", rewrite)
    report = ex._boot_exported(exe, frames=10, timeout=10)
    assert report["passed"] is False
    assert any("changed during boot" in reason for reason in report["errors"])


def test_executable_path_replacement_during_boot_does_not_pass(tmp_path, monkeypatch):
    exe = executable(tmp_path)
    previous = tmp_path / "old.x86_64"
    replacement = tmp_path / "replacement.x86_64"
    replacement.write_bytes(b"\x7fELF" + b"new-output" * 2048)

    def swap(command, cwd, timeout):
        exe.rename(previous)
        replacement.rename(exe)
        return 0, "", False

    monkeypatch.setattr(ex, "_run", swap)
    report = ex._boot_exported(exe, frames=10, timeout=10)
    assert report["passed"] is False
    assert any("changed during boot" in reason for reason in report["errors"])
    assert previous.is_file()


def test_removed_executable_during_boot_cannot_pass(tmp_path, monkeypatch):
    exe = executable(tmp_path)

    def unlink(command, cwd, timeout):
        exe.unlink()
        return 0, "", False

    monkeypatch.setattr(ex, "_run", unlink)
    report = ex._boot_exported(exe, frames=10, timeout=10)
    assert report["passed"] is False
    assert any("custody lost" in reason for reason in report["errors"])


def test_exit_code_or_timeout_are_not_synthetic_success(tmp_path, monkeypatch):
    exe = executable(tmp_path)
    for code, timed_out in ((23, False), (-1, True)):
        with monkeypatch.context() as scope:
            scope.setattr(ex, "_run", lambda *args: (code, "", timed_out))
            report = ex._boot_exported(exe, frames=10, timeout=5)
        assert report["passed"] is False
        if timed_out:
            assert any("timed out" in reason for reason in report["errors"])


def test_error_log_line_is_authoritative_even_on_zero_exit(tmp_path, monkeypatch):
    exe = executable(tmp_path)
    monkeypatch.setattr(
        ex, "_run",
        lambda *args: (0, "SCRIPT ERROR: invalid built game\n", False),
    )
    report = ex._boot_exported(exe, frames=10, timeout=5)
    assert report["passed"] is False
    assert report["errors"]


def test_export_receipt_contains_boot_failure_instead_of_raising(tmp_path, monkeypatch):
    files = emit_godot(compile_era("extraction_now"), title="boot custody review")
    monkeypatch.setattr(
        ex, "resolve_binary", lambda binary=None: ("/bin/true", "test", False),
    )

    def fake_export(cmd, cwd, timeout):
        if "--import" in cmd:
            return 0, "", False
        if "--export-release" in cmd:
            target = Path(cmd[-1])
            target.write_bytes(b"\x7fELF" + b"test" * 2048)
            target.with_suffix(".pck").write_bytes(b"pack" * 128)
            return 0, "", False
        raise AssertionError("unexpected Godot command")

    monkeypatch.setattr(ex, "_run", fake_export)
    monkeypatch.setattr(
        ex, "_boot_exported",
        lambda *args: (_ for _ in ()).throw(
            ValueError("exported executable path changed"),
        ),
    )
    receipt = ex.export_build(files, tmp_path / "out", presets=("Linux",))
    assert receipt["passed"] is False
    assert receipt["status"] == "failed"
    assert receipt["presets"]["Linux"]["reason"] == "boot-failed"
    assert receipt["presets"]["Linux"]["boot"]["passed"] is False
    assert receipt["release_certified"] is False
    assert receipt["device_qualified"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
