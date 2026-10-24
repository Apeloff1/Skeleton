"""Acceptance tests for exact tracked Git/VM parity without external network."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_codex_vm_parity.py"
spec = importlib.util.spec_from_file_location("audit_codex_vm_parity", SCRIPT)
assert spec and spec.loader
parity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parity)


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], check=True,
                            text=True, capture_output=True)
    return result.stdout.strip()


def fixture(tmp_path):
    remote = tmp_path / "upstream.git"
    checkout = tmp_path / "vm"
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "init", "-b", "main", str(checkout))
    git(checkout, "config", "user.name", "Audit Test")
    git(checkout, "config", "user.email", "audit@example.invalid")
    (checkout / "plain.txt").write_bytes(b"original\n")
    (checkout / "filename with space.txt").write_bytes(b" spaced\n")
    git(checkout, "add", ".")
    git(checkout, "commit", "-m", "baseline")
    git(checkout, "remote", "add", "origin", str(remote))
    git(checkout, "push", "-u", "origin", "main")
    return checkout


def scan(repo, **kwargs):
    return parity.audit(repo, remote="origin", branch="main", refresh=True,
                        include_ignored=False, **kwargs)


def test_clean_checkout_is_exactly_identical(tmp_path):
    repo = fixture(tmp_path)
    report = scan(repo)
    assert report["status"] == "identical"
    assert report["main_sha"] == report["local_head_sha"]
    assert report["tracked_paths"] == 2


def test_uncommitted_change_and_untracked_file_fail_closed(tmp_path):
    repo = fixture(tmp_path)
    (repo / "plain.txt").write_bytes(b"secret uncommitted change\n")
    (repo / "new.txt").write_bytes(b"not yet pushed\n")
    report = scan(repo)
    assert report["status"] == "diverged"
    assert "plain.txt" in report["findings"]["worktree_mismatch"]
    assert "new.txt" in report["findings"]["untracked"]


def test_staged_change_is_not_hidden_by_restored_worktree(tmp_path):
    repo = fixture(tmp_path)
    original = (repo / "plain.txt").read_bytes()
    (repo / "plain.txt").write_bytes(b"staged unpublished edit\n")
    git(repo, "add", "plain.txt")
    # The working tree now matches HEAD, but the index still differs.
    (repo / "plain.txt").write_bytes(original)
    report = scan(repo)
    assert report["main_sha"] == report["local_head_sha"]
    assert report["findings"]["worktree_mismatch"] == []
    assert report["findings"]["staged_index_difference"] == ["plain.txt"]
    assert report["status"] == "diverged"


def test_local_committed_changes_fail_canonical_main_comparison(tmp_path):
    repo = fixture(tmp_path)
    (repo / "plain.txt").write_text("new committed content", encoding="utf-8")
    git(repo, "commit", "-am", "VM has unpushed changes")
    report = scan(repo)
    assert report["status"] == "diverged"
    assert "plain.txt" in report["findings"]["head_tree_difference"]


def test_stale_local_checkout_detected_after_remote_advances(tmp_path):
    repo = fixture(tmp_path)
    clone = tmp_path / "other"
    git(tmp_path, "clone", "-b", "main", str(tmp_path / "upstream.git"), str(clone))
    git(clone, "config", "user.name", "Audit Test")
    git(clone, "config", "user.email", "audit@example.invalid")
    (clone / "plain.txt").write_text("upstream advanced\n", encoding="utf-8")
    git(clone, "commit", "-am", "upstream changed")
    git(clone, "push", "origin", "main")
    report = scan(repo)
    assert report["status"] == "diverged"
    assert report["main_sha"] != report["local_head_sha"]
    assert "plain.txt" in report["findings"]["worktree_mismatch"]


def test_same_tree_different_commit_is_not_vm_parity(tmp_path):
    repo = fixture(tmp_path)
    original = git(repo, "rev-parse", "HEAD")
    git(repo, "commit", "--allow-empty", "-m", "metadata only, tree unchanged")
    assert git(repo, "rev-parse", "HEAD") != original
    report = scan(repo)
    assert report["status"] == "diverged"
    assert report["findings"]["head_tree_difference"] == []
    assert report["findings"]["head_commit_difference"] == [
        git(repo, "rev-parse", "HEAD")
    ]


def test_fresh_fetch_without_independent_main_pin_does_not_certify(tmp_path):
    repo = fixture(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--fetch"],
        check=False, text=True, capture_output=True,
    )
    assert result.returncode != 0
    assert "--expected-main-sha" in result.stderr
    sha = git(repo, "rev-parse", "HEAD")
    pinned = subprocess.run(
        [
            sys.executable, str(SCRIPT), "--repo", str(repo),
            "--fetch", "--expected-main-sha", sha,
        ],
        check=False, text=True, capture_output=True,
    )
    assert pinned.returncode == 0, pinned.stderr
    assert '"status": "identical"' in pinned.stdout


def test_wrong_expected_main_sha_fails(tmp_path):
    repo = fixture(tmp_path)
    import pytest
    with pytest.raises(RuntimeError, match="not pinned expected main"):
        scan(repo, expected_sha="0" * 40)


def test_ignored_files_option_is_strict(tmp_path):
    repo = fixture(tmp_path)
    (repo / ".gitignore").write_text("*.cache\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-m", "ignore cache")
    git(repo, "push", "origin", "main")
    (repo / "output.cache").write_text("ephemeral", encoding="utf-8")
    assert scan(repo)["status"] == "identical"
    result = parity.audit(repo, remote="origin", branch="main", refresh=True,
                          include_ignored=True)
    assert result["status"] == "diverged"
    assert "output.cache" in result["findings"]["ignored"]


def test_symlink_target_and_executable_mode_are_verified(tmp_path):
    import os
    import pytest
    if os.name == "nt":
        pytest.skip("POSIX executable mode and symlink requirements")
    repo = fixture(tmp_path)
    link = repo / "linked.txt"
    link.symlink_to("plain.txt")
    run = repo / "run.sh"
    run.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    run.chmod(0o755)
    git(repo, "add", "linked.txt", "run.sh")
    git(repo, "commit", "-m", "add source link and executable")
    git(repo, "push", "origin", "main")
    assert scan(repo)["status"] == "identical"
    link.unlink()
    link.symlink_to("filename with space.txt")
    run.chmod(0o644)
    report = scan(repo)
    assert "linked.txt" in report["findings"]["worktree_mismatch"]
    assert any("run.sh" in x for x in report["findings"]["unexpected_type_or_mode"])


def test_tracking_ref_without_fetch_never_claims_live_parity(tmp_path):
    repo = fixture(tmp_path)
    report = parity.audit(repo, remote="origin", branch="main", refresh=False,
                          include_ignored=False)
    assert report["status"] == "identical"  # Local tree is identical to cached ref.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo)],
        check=False, text=True, capture_output=True,
    )
    assert result.returncode == 2
    assert '"status": "unverified_tracking_ref"' in result.stdout


def test_receipt_is_reproducible_and_json_must_not_contaminate_checkout(tmp_path):
    repo = fixture(tmp_path)
    a, b = scan(repo), scan(repo)
    assert a["evidence_sha256"] == b["evidence_sha256"]
    assert len(a["evidence_sha256"]) == 64
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--fetch", "--json", str(repo / "audit.json")],
        check=False, text=True, capture_output=True,
    )
    assert result.returncode != 0
    assert "receipt must be outside" in result.stderr
    assert not (repo / "audit.json").exists()


def test_symlinked_parent_directory_cannot_appeal_to_identical_external_bytes(tmp_path):
    repo = fixture(tmp_path)
    nested = repo / "nested"
    nested.mkdir()
    (nested / "record.bin").write_bytes(b"same committed bytes\n")
    git(repo, "add", "nested/record.bin")
    git(repo, "commit", "-m", "nested source")
    git(repo, "push", "origin", "main")

    stored = tmp_path / "saved-dir"
    nested.rename(stored)
    external = tmp_path / "external"
    external.mkdir()
    (external / "record.bin").write_bytes((stored / "record.bin").read_bytes())
    nested.symlink_to(external, target_is_directory=True)

    report = scan(repo)
    assert report["status"] == "diverged"
    assert any(
        "nested/record.bin" in finding and "ancestor" in finding
        for finding in report["findings"]["unexpected_type_or_mode"]
    )
