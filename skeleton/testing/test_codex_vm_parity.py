"""Local stdlib-only regression coverage for Codex-to-VM source parity."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess

import pytest

MODULE = Path(__file__).resolve().parents[2] / "scripts" / "check_codex_vm_parity.py"
spec = importlib.util.spec_from_file_location("check_codex_vm_parity", MODULE)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def pair(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    run(source, "init", "-q")
    (source / "file.py").write_text("print('known')\n", encoding="utf-8")
    (source / "nested").mkdir()
    (source / "nested" / "receipt.json").write_text('{"ok":true}\n', encoding="utf-8")
    run(source, "add", "-A")
    run(source, "-c", "user.name=Parity Test", "-c", "user.email=parity@example.invalid", "commit", "-qm", "source")
    vm = tmp_path / "vm"
    run(tmp_path, "clone", "-q", str(source), str(vm))
    sha = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    return source, vm, sha


def test_identical_clean_checkouts_have_receipt(pair):
    src, vm, sha = pair
    receipt = mod.compare(src, vm, sha)
    assert receipt["verdict"] == "identical_tracked_source"
    assert receipt["required_commit"] == sha
    assert receipt["tracked_files"] == 2
    assert len(receipt["source_receipt_sha256"]) == 64
    assert "running_vm_process_state" in receipt["excluded"]


def test_wrong_commit_fails_closed(pair):
    src, vm, sha = pair
    with pytest.raises(mod.ParityError, match="required GitHub main SHA"):
        mod.compare(src, vm, "a" * 40 if sha != "a" * 40 else "b" * 40)


def test_dirty_vm_fails_closed(pair):
    src, vm, sha = pair
    (vm / "file.py").write_text("modified\n", encoding="utf-8")
    with pytest.raises(mod.ParityError, match="modified"):
        mod.compare(src, vm, sha)


def test_untracked_file_fails_closed(pair):
    src, vm, sha = pair
    (vm / "untracked.py").write_text("hidden new work\n", encoding="utf-8")
    with pytest.raises(mod.ParityError, match="untracked"):
        mod.compare(src, vm, sha)


def test_identical_root_is_not_two_attestations(pair):
    src, vm, sha = pair
    with pytest.raises(mod.ParityError, match="distinct"):
        mod.compare(src, src, sha)


def test_missing_checkout_fails_closed(pair, tmp_path):
    src, vm, sha = pair
    with pytest.raises(mod.ParityError, match="unavailable"):
        mod.compare(src, tmp_path / "not-a-vm", sha)


def test_symlink_targets_must_be_identical(pair):
    src, vm, sha = pair
    (src / "shortcut").symlink_to("file.py")
    run(src, "add", "shortcut")
    run(src, "-c", "user.name=Parity Test", "-c", "user.email=parity@example.invalid", "commit", "-qm", "symlink")
    run(vm, "pull", "-q", "--ff-only")
    sha = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    assert mod.compare(src, vm, sha)["tracked_files"] == 3
    (vm / "shortcut").unlink()
    (vm / "shortcut").symlink_to("nested/receipt.json")
    with pytest.raises(mod.ParityError, match="modified"):
        mod.compare(src, vm, sha)


def test_executable_bit_mismatch_fails_closed(pair):
    if os.name == "nt":
        pytest.skip("POSIX executable bit required")
    src, vm, sha = pair
    os.chmod(vm / "file.py", 0o755)
    with pytest.raises(mod.ParityError):
        mod.compare(src, vm, sha)


def test_reject_unsafe_required_sha(pair):
    src, vm, _sha = pair
    with pytest.raises(mod.ParityError, match="full lowercase"):
        mod.compare(src, vm, "main")
