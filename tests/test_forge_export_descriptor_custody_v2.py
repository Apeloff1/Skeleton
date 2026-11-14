"""Descriptor-anchored Godot export custody, resource budgets and mirror parity.

These source-level tests do not claim Godot template, device or binary boot
qualification. Integration cases drive the real exporter with a fake bounded
runner and ensure no synthetic report confers release/device approval.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat

import pytest

from skeleton.forge import export as ex
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="requires POSIX descriptor-relative artifact custody",
)


def test_one_regular_artifact_digest_and_size(tmp_path: Path) -> None:
    artifact = tmp_path / "game.pck"
    content = b"native-resource" * 256
    artifact.write_bytes(content)
    digest, size = ex._artifact_evidence(artifact)
    assert digest == hashlib.sha256(content).hexdigest()
    assert ex._artifact_digest(artifact) == digest
    assert size == len(content)


def test_symlinked_ancestor_never_reaches_foreign_artifact(tmp_path: Path) -> None:
    safe = tmp_path / "outside"
    safe.mkdir()
    artifact = safe / "resource.pck"
    artifact.write_bytes(b"foreign source")
    alias = tmp_path / "alias"
    alias.symlink_to(safe, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        ex._artifact_evidence(alias / "resource.pck")


def test_final_symlink_and_nonregular_file_are_refused(tmp_path: Path) -> None:
    artifact = tmp_path / "real.pck"
    artifact.write_bytes(b"native")
    alias = tmp_path / "alias.pck"
    alias.symlink_to(artifact)
    with pytest.raises((ValueError, OSError)):
        ex._artifact_digest(alias)
    with pytest.raises((ValueError, OSError)):
        ex._artifact_evidence(tmp_path)
    if hasattr(os, "mkfifo"):
        pipe = tmp_path / "pipe.pck"
        os.mkfifo(pipe)
        with pytest.raises(ValueError):
            ex._artifact_digest(pipe)


def test_intermediate_ancestor_swap_before_open_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    source = safe / "binary.pck"
    source.write_bytes(b"safe")
    outside = tmp_path / "foreign"
    outside.mkdir()
    (outside / "binary.pck").write_bytes(b"unsafe")
    old = tmp_path / "old-safe"
    original_open = os.open
    swapped = False

    def swap(name, flags, *args, **kwargs):
        nonlocal swapped
        if name == "safe" and kwargs.get("dir_fd") is not None and not swapped:
            safe.rename(old)
            safe.symlink_to(outside, target_is_directory=True)
            swapped = True
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(ex.os, "open", swap)
    with pytest.raises((ValueError, OSError)):
        ex._artifact_digest(source)
    assert swapped
    assert (outside / "binary.pck").read_bytes() == b"unsafe"


def test_intermediate_ancestor_swap_during_stream_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe = tmp_path / "safe"
    safe.mkdir()
    source = safe / "resource.pck"
    source.write_bytes(b"a" * 32768)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "resource.pck").write_bytes(b"z" * 32768)
    old = tmp_path / "old-safe"
    original_read = os.read
    swapped = False

    def replace_during_read(fd: int, count: int):
        nonlocal swapped
        chunk = original_read(fd, count)
        if chunk and not swapped and stat.S_ISREG(os.fstat(fd).st_mode):
            safe.rename(old)
            safe.symlink_to(foreign, target_is_directory=True)
            swapped = True
        return chunk

    monkeypatch.setattr(ex.os, "read", replace_during_read)
    with pytest.raises(ValueError, match="parent changed"):
        ex._artifact_evidence(source)
    assert swapped
    assert (foreign / "resource.pck").read_bytes() == b"z" * 32768


def test_same_size_mutation_during_hash_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "texture.pck"
    source.write_bytes(b"a" * 8192)
    original_read = os.read
    mutated = False

    def mutate_on_read(fd: int, size: int):
        nonlocal mutated
        chunk = original_read(fd, size)
        if chunk and not mutated:
            mutated = True
            source.write_bytes(b"b" * 8192)
        return chunk

    monkeypatch.setattr(ex.os, "read", mutate_on_read)
    with pytest.raises(ValueError, match="changed"):
        ex._artifact_evidence(source)
    assert mutated


def test_byte_budget_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    artifact = tmp_path / "large.pck"
    artifact.write_bytes(b"m" * 4096)
    monkeypatch.setattr(ex, "MAX_OUTPUT_BYTES", 512)
    with pytest.raises(ValueError, match="oversized"):
        ex._artifact_evidence(artifact)


def test_inventory_is_bounded_before_entire_directory_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for number in range(6):
        (tmp_path / f"file-{number:03d}.pck").write_bytes(b"payload")
    monkeypatch.setattr(ex, "MAX_OUTPUT_FILES", 4)
    with pytest.raises(ValueError, match="file budget"):
        ex._bounded_output_inventory(tmp_path)


def test_inventory_is_sorted_and_rejects_special_entries(tmp_path: Path) -> None:
    (tmp_path / "z.pck").write_bytes(b"z")
    (tmp_path / "a.pck").write_bytes(b"a")
    assert [p.name for p in ex._bounded_output_inventory(tmp_path)] == [
        "a.pck", "z.pck",
    ]
    (tmp_path / "nested").mkdir()
    with pytest.raises(ValueError, match="unsafe"):
        ex._bounded_output_inventory(tmp_path)


def test_unsafe_parent_directory_and_dot_dot_are_refused(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        ex._bounded_output_inventory(alias)
    with pytest.raises(ValueError, match="traversal"):
        ex._safe_directory(tmp_path / "actual" / ".." / "unexpected")


def test_ai_mirror_is_byte_identical_after_source_repair() -> None:
    root = Path(__file__).resolve().parents[1]
    canonical = root / "skeleton/forge/export.py"
    mirrored = root / "skeleton/ai/forge/export.py"
    assert canonical.read_bytes() == mirrored.read_bytes()


def fake_runner(command, _cwd, _timeout):
    if "--import" in command:
        return 0, "", False
    if "--export-release" in command:
        target = Path(command[-1])
        target.write_bytes(b"\x7fELF" + b"f" * 8192)
        if "Linux" in command:
            target.with_suffix(".pck").write_bytes(b"resources" * 256)
        return 0, "", False
    raise AssertionError(f"unexpected subprocess: {command!r}")


def test_full_source_export_receipt_does_not_claim_release_or_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = emit_godot(compile_era("extraction_now"), title="review")
    monkeypatch.setattr(
        ex, "resolve_binary", lambda binary=None: ("/bin/true", "mock-runner", False),
    )
    monkeypatch.setattr(ex, "_run", fake_runner)
    monkeypatch.setattr(
        ex, "_boot_exported",
        lambda target, frames, timeout: {
            "returncode": 0, "timed_out": False, "errors": [],
            "passed": True, "log_tail": "",
        },
    )
    report = ex.export_build(
        files, tmp_path / "native-out", presets=("Linux",),
    )
    assert report["passed"] is True
    assert report["status"] == "passed"
    assert report["release_certified"] is False
    assert report["device_qualified"] is False
    linux = report["presets"]["Linux"]
    assert linux["sha256"]["linux/game.x86_64"]
    assert linux["sha256"]["linux/game.pck"]
    assert linux["bytes"] == (
        (tmp_path / "native-out/linux/game.x86_64").stat().st_size
        + (tmp_path / "native-out/linux/game.pck").stat().st_size
    )


def test_aggregate_output_budget_refuses_synthetic_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = emit_godot(compile_era("extraction_now"), title="review")
    monkeypatch.setattr(
        ex, "resolve_binary", lambda binary=None: ("/bin/true", "mock-runner", False),
    )
    monkeypatch.setattr(ex, "_run", fake_runner)
    monkeypatch.setattr(ex, "MAX_OUTPUT_BYTES", 9000)
    result = ex.export_build(
        files, tmp_path / "native-out", presets=("Linux",),
    )
    assert result["passed"] is False
    assert result["presets"]["Linux"]["reason"] == "artifact-custody-failed"
    assert result["release_certified"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
