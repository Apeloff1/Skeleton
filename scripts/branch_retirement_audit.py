#!/usr/bin/env python3
"""Read-only, lease-pinned local branch retirement review.

This reports candidates for human review; it never deletes a Git reference.
Remote GitHub branches not fetched into this checkout are NOT enumerated.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from skeleton.repo_intelligence.git_index import GitIndex


_PROTECTED = ("release/", "hotfix/", "backup/", "archive/", "protected/")
_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class RefAuditError(RuntimeError):
    pass


def _run(scanner: GitIndex, *args: str, allow_one: bool = False) -> tuple[int, str]:
    try:
        call = subprocess.run(
            ["git", "-c", "core.fsmonitor=false",
             "-c", "core.untrackedCache=false", "-c", "diff.external=", *args],
            cwd=scanner.root, env=GitIndex._safe_git_environment(),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=scanner.timeout_seconds,
            check=False, shell=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RefAuditError("Git ref inspection did not finish") from exc
    if call.returncode not in ((0, 1) if allow_one else (0,)):
        raise RefAuditError("Git ref inspection failed (code %d)" % call.returncode)
    try:
        decoded = call.stdout.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise RefAuditError("non-UTF8 branch metadata must be reviewed separately") from exc
    return call.returncode, decoded.strip()


def _heads(scanner: GitIndex, *, max_branches: int) -> tuple[tuple[str, str], ...]:
    _, raw = _run(scanner, "show-ref", "--heads")
    output: list[tuple[str, str]] = []
    for line in raw.splitlines():
        sha, sep, ref = line.partition(" ")
        if not sep or not _SHA.fullmatch(sha) or not ref.startswith("refs/heads/"):
            raise RefAuditError("malformed branch ref record")
        if not ref[len("refs/heads/"):]:
            raise RefAuditError("missing branch name")
        output.append((ref, sha))
        if len(output) > max_branches:
            raise RefAuditError("local branch count exceeds explicit audit bound")
    if len(set(ref for ref, _ in output)) != len(output):
        raise RefAuditError("duplicate branch names")
    return tuple(sorted(output))


def _tree(scanner: GitIndex, commit: str) -> str:
    _, value = _run(scanner, "rev-parse", "--verify", commit + "^{tree}")
    if not _SHA.fullmatch(value):
        raise RefAuditError("invalid resolved Git tree identity")
    return value


def classify_ref(*, name: str, head: str, main: str, tree: str, main_tree: str,
                 is_ancestor: bool, main_is_ancestor: bool) -> str:
    if name == "main" or name == "master" or name.startswith(_PROTECTED):
        return "protected_keep"
    if head == main:
        return "same_head_review"
    if tree == main_tree:
        return "identical_tree_review"
    if is_ancestor:
        return "ancestor_review"
    if main_is_ancestor:
        return "ahead_of_main_keep"
    return "diverged_keep"


def audit(scanner: GitIndex, *, max_branches: int = 1500) -> dict[str, object]:
    if not 1 <= max_branches <= 10000:
        raise RefAuditError("invalid branch audit cap")
    initial = _heads(scanner, max_branches=max_branches)
    lookup = dict(initial)
    main = lookup.get("refs/heads/main")
    if main is None:
        raise RefAuditError("local main is unavailable; do not infer remote coverage")
    main_tree = _tree(scanner, main)
    rows: list[dict[str, object]] = []
    for ref, sha in initial:
        if ref == "refs/heads/main":
            continue
        tree = _tree(scanner, sha)
        ancestor = _run(scanner, "merge-base", "--is-ancestor", sha, main, allow_one=True)[0] == 0
        main_ancestor = _run(scanner, "merge-base", "--is-ancestor", main, sha, allow_one=True)[0] == 0
        name = ref[len("refs/heads/"):]
        classification = classify_ref(
            name=name, head=sha, main=main, tree=tree, main_tree=main_tree,
            is_ancestor=ancestor, main_is_ancestor=main_ancestor,
        )
        rows.append({
            "ref": ref, "head_sha": sha, "tree_sha": tree,
            "classification": classification,
            "ancestor_of_main": ancestor,
            "main_ancestor_of_branch": main_ancestor,
            "matches_main_tree": tree == main_tree,
            "automatic_deletion_allowed": False,
        })
    if _heads(scanner, max_branches=max_branches) != initial:
        raise RefAuditError("branch refs moved during audit; discard stale results")
    return {
        "schema": "skeleton.branch_retirement.review.v1",
        "scope": "local_refs_heads_only",
        "remote_coverage_complete": False,
        "main_sha": main, "main_tree_sha": main_tree,
        "local_branch_count": len(initial),
        "reviewed_non_main_count": len(rows),
        "automatic_deletion_allowed": False,
        "classification_not_deletion_authorization": True,
        "branches": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--max-branches", type=int, default=1500)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.expanduser().absolute()
    if target.is_symlink() or target.exists() or not target.parent.is_dir():
        parser.error("select a new, non-symlink output in an existing directory")
    # GitIndex validates that --root is the real worktree top level.
    result = audit(GitIndex(args.root), max_branches=args.max_branches)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    try:
        with open(target, "x", encoding="utf-8") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise RefAuditError("output appeared during audit; refusing overwrite") from exc
    print("branch audit: %d local non-main refs; 0 deletions"
          % result["reviewed_non_main_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
