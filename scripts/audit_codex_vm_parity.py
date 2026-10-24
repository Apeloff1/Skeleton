#!/usr/bin/env python3
"""Fail-closed byte parity audit for a Codex VM checkout against canonical main.

Run in the VM: python scripts/audit_codex_vm_parity.py --fetch --json /tmp/codex-parity.json
A result of 'identical' is meaningful only for the exact fetched target commit,
tracked working-tree bytes, file modes, symlinks, submodules and untracked files.
Ignored local build/cache files can be included with --include-ignored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

HEX_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=240,
    )
    if result.returncode:
        raise RuntimeError(
            "git " + " ".join(args) + " failed: "
            + result.stderr.decode("utf-8", errors="replace")[:1200]
        )
    return result.stdout


def paths_from_null(data: bytes) -> list[str]:
    return [os.fsdecode(value) for value in data.split(b"\0") if value]


def tree(repo: Path, commit: str) -> dict[str, tuple[str, str, str]]:
    result: dict[str, tuple[str, str, str]] = {}
    for row in git(repo, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not row:
            continue
        header, name = row.split(b"\t", 1)
        mode, kind, blob = header.decode("ascii").split(" ")
        result[os.fsdecode(name)] = (mode, kind, blob)
    return result


def working_git_blob_sha(path: Path, *, algorithm: str, symbolic: bool) -> str:
    if symbolic:
        raw = os.fsencode(os.readlink(path))
        digest = hashlib.new(algorithm)
        digest.update(f"blob {len(raw)}\0".encode("ascii"))
        digest.update(raw)
    else:
        size = path.stat().st_size
        digest = hashlib.new(algorithm)
        digest.update(f"blob {size}\0".encode("ascii"))
        with path.open("rb") as handle:
            while chunk := handle.read(1 << 20):
                digest.update(chunk)
    return digest.hexdigest()


def audit(repo: Path, *, remote: str, branch: str, refresh: bool, include_ignored: bool,
          expected_sha: str | None = None, max_detail: int = 100) -> dict[str, Any]:
    root = Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel").strip())).resolve()
    if repo.resolve() != root:
        repo = root
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", remote):
        raise ValueError("remote must be a simple Git remote name")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch) or branch.startswith("-") or ".." in branch:
        raise ValueError("invalid remote branch")
    if refresh:
        git(repo, "fetch", "--no-tags", remote,
            f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}")
    target = git(repo, "rev-parse", "--verify", f"refs/remotes/{remote}/{branch}^{{commit}}").decode().strip()
    head = git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if expected_sha is not None and target != expected_sha:
        raise RuntimeError(f"fetched target {target} is not pinned expected main {expected_sha}")
    algorithm = git(repo, "rev-parse", "--show-object-format").decode().strip()
    if algorithm not in {"sha1", "sha256"}:
        raise RuntimeError("unsupported Git object algorithm")
    expected = tree(repo, target)
    current = tree(repo, head)
    distinct_tree = sorted(p for p in expected.keys() | current.keys() if expected.get(p) != current.get(p))
    findings: dict[str, list[str]] = {
        # Equal trees do not imply the VM has the same exact commit.
        # An empty commit or metadata-only revision must not certify parity.
        "head_commit_difference": [] if head == target else [head],
        "head_tree_difference": distinct_tree,
        "worktree_mismatch": [],
        "missing_worktree_file": [],
        "unexpected_type_or_mode": [],
        "submodule_mismatch": [],
        "untracked": paths_from_null(git(repo, "ls-files", "--others", "--exclude-standard", "-z")),
        "ignored": [],
    }
    if include_ignored:
        findings["ignored"] = paths_from_null(git(repo, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"))
    for relative, (mode, kind, digest) in expected.items():
        path = repo / relative
        if not os.path.lexists(path):
            findings["missing_worktree_file"].append(relative)
            continue
        if kind == "commit":
            if not path.is_dir():
                findings["submodule_mismatch"].append(relative + ": missing submodule directory")
                continue
            try:
                actual = git(path, "rev-parse", "HEAD").decode().strip()
                dirty = bool(git(path, "status", "--porcelain", "--untracked-files=all"))
                if actual != digest or dirty:
                    findings["submodule_mismatch"].append(relative + ": SHA or files differ")
            except RuntimeError:
                findings["submodule_mismatch"].append(relative + ": unavailable checkout")
            continue
        if kind != "blob":
            findings["unexpected_type_or_mode"].append(relative + ": unexpected git object")
            continue
        symlink = mode == "120000"
        if symlink != path.is_symlink() or (not symlink and not path.is_file()):
            findings["unexpected_type_or_mode"].append(relative + ": changed file type")
            continue
        if os.name != "nt" and not symlink:
            executable = bool(path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
            if executable != (mode == "100755"):
                findings["unexpected_type_or_mode"].append(relative + ": executable bit differs")
        if working_git_blob_sha(path, algorithm=algorithm, symbolic=symlink) != digest:
            findings["worktree_mismatch"].append(relative)
    for items in findings.values():
        items.sort()
    # The full path list is included in the file; truncate stdout separately.
    counts = {key: len(value) for key, value in findings.items()}
    identical = all(value == 0 for value in counts.values())
    canonical_receipt = json.dumps(
        {"target": target, "head": head, "object_format": algorithm,
         "tracked_paths": len(expected), "findings": findings},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return {
        "evidence_sha256": hashlib.sha256(canonical_receipt).hexdigest(),
        "schema": "skeleton.codex-vm-byte-parity.v1",
        "status": "identical" if identical else "diverged",
        "scope": "git tree, tracked physical bytes/modes/symlinks, submodules, and untracked files"
                 + (" including ignored files" if include_ignored else " excluding ignored build artifacts"),
        "repo": str(repo),
        "remote": remote,
        "branch": branch,
        "fetched": refresh,
        "main_sha": target,
        "local_head_sha": head,
        "object_format": algorithm,
        "tracked_paths": len(expected),
        "counts": counts,
        "findings": {key: values[:max_detail] for key, values in findings.items()},
        "omitted_details": {key: max(0, len(value) - max_detail) for key, value in findings.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--fetch", action="store_true", help="Require fresh remote main custody")
    parser.add_argument("--expected-main-sha", default=None)
    parser.add_argument("--include-ignored", action="store_true")
    parser.add_argument("--max-detail", type=int, default=100)
    parser.add_argument("--json", type=Path, default=None, help="Write machine-readable audit result")
    args = parser.parse_args()
    if args.expected_main_sha and not HEX_SHA.fullmatch(args.expected_main_sha):
        parser.error("--expected-main-sha must be a full Git SHA")
    # A Git remote named origin is not itself proof of GitHub main. Do not
    # promote a freshly fetched local or misconfigured remote to authority
    # unless its exact SHA was independently checked before invocation.
    if args.fetch and not args.expected_main_sha:
        parser.error("--fetch requires an independently verified --expected-main-sha")
    if args.max_detail < 0:
        parser.error("--max-detail must not be negative")
    if args.json:
        try:
            root = Path(os.fsdecode(git(args.repo, "rev-parse", "--show-toplevel").strip())).resolve()
            if args.json.resolve().is_relative_to(root):
                parser.error("--json receipt must be outside the audited checkout")
        except (RuntimeError, OSError) as exc:
            parser.error("cannot establish auditable repository root: " + str(exc)[:500])
    try:
        result = audit(args.repo, remote=args.remote, branch=args.branch,
                       refresh=args.fetch, include_ignored=args.include_ignored,
                       expected_sha=args.expected_main_sha, max_detail=args.max_detail)
        # A local tracking ref without a fresh fetch cannot prove remote parity.
        if not args.fetch:
            result["status"] = "unverified_tracking_ref" if result["status"] == "identical" else "diverged"
        code = 0 if result["status"] == "identical" else 2
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        result = {"schema": "skeleton.codex-vm-byte-parity.v1", "status": "error",
                  "error": str(exc)[:1400]}
        code = 3
    data = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if args.json:
        args.json.write_text(data, encoding="utf-8")
    print(data)
    return code


if __name__ == "__main__":
    sys.exit(main())
