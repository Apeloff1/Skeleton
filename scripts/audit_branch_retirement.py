#!/usr/bin/env python3
"""Read-only, lease-aware candidate census; NEVER deletes a Git branch.

This is an operator report for issue #3791. Git ancestry alone is not proof
that a historical ref can be discarded: active PRs, owners and custody matter.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys


_SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_PROTECTED = ("main", "master", "release/", "backup/", "archive/", "protect/")


class RetirementAuditError(RuntimeError):
    """Stable fail-closed refusal of incomplete Git evidence."""


def _git(root: Path, *args: str) -> str:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false",
         "-c", "core.untrackedCache=false",
         "-c", "diff.external=", *args],
        cwd=root, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=45,
    )
    if result.returncode:
        raise RetirementAuditError(f"Git metadata query failed ({args[0]})")
    try:
        return result.stdout.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise RetirementAuditError("non-UTF8 ref metadata") from exc


def audit(
    root: Path, *, expected_main: str,
    as_of: int, min_age_days: int = 30,
    max_branches: int = 100_000,
) -> dict[str, object]:
    if not _SHA.fullmatch(expected_main):
        raise RetirementAuditError("expected_main must be a full Git SHA")
    if (type(as_of) is not int or as_of <= 0
            or type(min_age_days) is not int or min_age_days < 1
            or type(max_branches) is not int or max_branches < 1):
        raise RetirementAuditError("invalid audit limits")
    root = root.resolve()
    actual_root = _git(root, "rev-parse", "--show-toplevel").strip()
    if Path(actual_root).resolve() != root:
        raise RetirementAuditError("root must be repository top level")
    main = _git(root, "rev-parse", "--verify", "refs/heads/main^{commit}").strip()
    if main != expected_main:
        raise RetirementAuditError("main moved: expected SHA lease is stale")
    main_tree = _git(root, "rev-parse", "--verify", main + "^{tree}").strip()
    if not _SHA.fullmatch(main_tree):
        raise RetirementAuditError("invalid main tree object identity")

    # Ask Git for the exact immutable object identity of every local branch.
    # A refs/heads scope deliberately excludes remote-tracking and tags.
    listing = _git(
        root, "for-each-ref",
        "--format=%(refname)%00%(objectname)%00%(committerdate:unix)",
        "refs/heads/",
    )
    rows = []
    names: set[str] = set()
    for line in listing.splitlines():
        parts = line.split("\0")
        if len(parts) != 3:
            raise RetirementAuditError("malformed branch metadata")
        ref, sha, timestamp = parts
        if not ref.startswith("refs/heads/") or not _SHA.fullmatch(sha):
            raise RetirementAuditError("invalid ref or object identity")
        name = ref[len("refs/heads/"):]
        if not name or name in names:
            raise RetirementAuditError("duplicate or empty branch name")
        names.add(name)
        try:
            commit_time = int(timestamp)
        except ValueError as exc:
            raise RetirementAuditError("invalid commit timestamp") from exc
        if commit_time < 0 or commit_time > as_of:
            raise RetirementAuditError("future or invalid commit timestamp")
        rows.append((name, sha, commit_time))
        if len(rows) > max_branches:
            raise RetirementAuditError("branch count exceeds bounded audit limit")
    if "main" not in names:
        raise RetirementAuditError("main branch missing from exhaustive refs")
    if _git(root, "rev-parse", "--verify", "refs/heads/main^{commit}").strip() != main:
        raise RetirementAuditError("main changed while enumerating refs")

    report = []
    for name, sha, commit_time in sorted(rows):
        # Git's ancestor check returns 1 for "not ancestor", so query ahead
        # and behind counts using rev-list --left-right --count instead.
        # The enumerated SHA values are the custody contract. Using mutable
        # branch names here could produce a mixed-time ancestry decision.
        counts = _git(root, "rev-list", "--left-right", "--count",
                      main + "..." + sha).strip().split()
        if len(counts) != 2 or not all(item.isdecimal() for item in counts):
            raise RetirementAuditError("invalid Git ancestry count")
        behind, ahead = (int(item) for item in counts)
        tip_tree = _git(root, "rev-parse", "--verify", sha + "^{tree}").strip()
        if not _SHA.fullmatch(tip_tree):
            raise RetirementAuditError("invalid pinned branch tree identity")
        same_tree = tip_tree == main_tree
        protected = (name in _PROTECTED
                     or any(name.startswith(prefix) for prefix in _PROTECTED if prefix.endswith("/")))
        old_enough = as_of - commit_time >= min_age_days * 86400
        reason = (
            "protected_name" if protected
            else "tree_equivalent_but_divergent_history" if same_tree and ahead
            else "divergent_history" if ahead
            else "young_ref" if not old_enough
            else "ancestor_only_requires_external_pr_and_owner_review"
        )
        report.append({
            "branch": name, "tip_sha": sha,
            "tree_sha": tip_tree,
            "content_equivalent_to_main": same_tree,
            "commit_time": commit_time,
            "ahead": ahead, "behind": behind,
            "age_days": (as_of - commit_time) // 86400,
            "ancestry_candidate": not protected and not ahead and old_enough,
            "reason": reason,
            "deletion_authorized": False,
        })
    # Final immutable lease check. This is a report, not an approved deletion
    # window. The GitHub PR/ruleset API must also be checked at execution time.
    after = _git(root, "for-each-ref",
                 "--format=%(refname)%00%(objectname)%00%(committerdate:unix)",
                 "refs/heads/")
    if listing != after:
        raise RetirementAuditError("branch references moved during audit")
    return {
        "schema": "skeleton.branches.retirement-audit.v1",
        "head": main, "main_tree_sha": main_tree,
        "scope": "local_refs_heads_only",
        "remote_coverage_complete": False,
        "as_of": as_of,
        "generated_at": datetime.fromtimestamp(as_of, tz=timezone.utc).isoformat(),
        "branch_count": len(report),
        "ancestry_candidates": sum(row["ancestry_candidate"] for row in report),
        "refs": report,
        "all_deletion_authorized": False,
        "requires_live_github_pr_checks": True,
        "coverage_complete": True,  # exhaustive LOCAL refs/heads only
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--expected-main", required=True)
    parser.add_argument("--as-of", type=int, required=True, help="Unix epoch for reproducible age filtering")
    parser.add_argument("--age-days", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.root, expected_main=args.expected_main, as_of=args.as_of, min_age_days=args.age_days)
    output = args.output.absolute()
    if not output.parent.is_dir() or output.exists() or output.is_symlink():
        parser.error("output directory must exist and destination must not already exist")
    # Exclusive creation, never truncate existing operator evidence.
    with output.open("x", encoding="utf-8") as destination:
        json.dump(report, destination, indent=2, sort_keys=True)
        destination.write("\n")
    print(f"read-only branches={report['branch_count']} review_candidates={report['ancestry_candidates']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RetirementAuditError as exc:
        print(f"branch audit refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
