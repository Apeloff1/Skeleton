"""Pinned, read-only branch audit; does not delete repository data."""
from __future__ import annotations

from pathlib import Path
import subprocess
import time

import pytest

from scripts.audit_branch_retirement import RetirementAuditError, audit


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def repo(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "audit@example.invalid")
    git(root, "config", "user.name", "Evidence Fixture")
    (root / "a.txt").write_text("alpha\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "root")
    return root


def test_complete_census_distinguishes_ancestor_divergent_and_protected(tmp_path):
    root = repo(tmp_path)
    git(root, "branch", "fix/old-ancestor")
    git(root, "branch", "backup/immutable")
    git(root, "checkout", "-q", "-b", "feat/divergent")
    (root / "a.txt").write_text("new\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "diverged")
    git(root, "checkout", "-q", "main")
    before = git(root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads")
    head = git(root, "rev-parse", "main")
    at = int(time.time()) + 45 * 86400
    r = audit(root, expected_main=head, as_of=at, min_age_days=30)
    rows = {item["branch"]: item for item in r["refs"]}
    assert len(rows) == r["branch_count"] == 4
    assert rows["fix/old-ancestor"]["ancestry_candidate"] is True
    assert rows["feat/divergent"]["ahead"] == 1
    assert rows["feat/divergent"]["ancestry_candidate"] is False
    assert rows["backup/immutable"]["reason"] == "protected_name"
    assert rows["main"]["deletion_authorized"] is False
    assert all(not item["deletion_authorized"] for item in rows.values())
    assert r["all_deletion_authorized"] is False
    assert r["coverage_complete"] is True
    assert git(root, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads") == before


def test_mismatched_main_sha_and_invalid_ranges_refuse(tmp_path):
    root = repo(tmp_path)
    head = git(root, "rev-parse", "main")
    at = int(time.time()) + 45 * 86400
    with pytest.raises(RetirementAuditError, match="main moved"):
        audit(root, expected_main="f" * 40, as_of=at)
    with pytest.raises(RetirementAuditError, match="audit limits"):
        audit(root, expected_main=head, as_of=at, min_age_days=0)
    with pytest.raises(RetirementAuditError, match="audit limits"):
        audit(root, expected_main=head, as_of=at, max_branches=0)
    with pytest.raises(RetirementAuditError, match="count exceeds"):
        audit(root, expected_main=head, as_of=at, max_branches=0+0+0+0+0)  # same hard limit


def test_young_branch_is_never_retirement_candidate(tmp_path):
    root = repo(tmp_path)
    git(root, "branch", "fix/fresh")
    head = git(root, "rev-parse", "main")
    out = audit(root, expected_main=head, as_of=int(time.time()) + 3600)
    row = next(item for item in out["refs"] if item["branch"] == "fix/fresh")
    assert row["ahead"] == 0
    assert row["reason"] == "young_ref"
    assert row["ancestry_candidate"] is False
