#!/usr/bin/env python3
"""Read-only, commit-pinned inventory of legacy branch changes against main.

Tracks paths changed since merge base, not GitHub's misleading ahead-commit count.
Identical blobs/modes establish byte equality only, never semantic equivalence,
branch-retirement authorization, or a successful test/merge.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
REF = re.compile(r"refs/(?:heads|remotes/origin)/[A-Za-z0-9_./-]+\Z")


class AuditError(ValueError):
    """Pinned Git inventory cannot be safely established."""


def git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-c", "diff.external=", *args],
            cwd=root, input=b"", capture_output=True, check=True, timeout=45,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise AuditError("unable to verify git object or branch ref") from exc


def commit(root: Path, ref: str) -> str:
    if not REF.fullmatch(ref) or ".." in ref or "/./" in ref or ref.endswith("/"):
        raise AuditError("expected an explicit, well-formed local or origin ref")
    result = git(root, "rev-parse", "--verify", ref + "^{commit}").decode("ascii").strip()
    if not SHA.fullmatch(result):
        raise AuditError("invalid commit SHA from Git")
    return result


def tree(root: Path, sha: str) -> dict[str, tuple[str, str]]:
    """Read complete immutable file inventory; include executable/mode changes."""
    if not SHA.fullmatch(sha):
        raise AuditError("invalid pinned commit SHA")
    entries = {}
    for row in git(root, "ls-tree", "-r", "-z", "--full-tree", sha).split(b"\0"):
        if not row:
            continue
        try:
            meta, path = row.split(b"\t", 1)
            mode, kind, digest = meta.decode("ascii").split()
            name = path.decode("utf-8", "strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise AuditError("malformed or non-UTF8 Git tree path") from exc
        if kind not in ("blob", "commit") or not SHA.fullmatch(digest) or name in entries:
            raise AuditError("invalid tree object or duplicate path")
        entries[name] = (mode, digest)
    return entries


def audit(root: Path, *, main_ref: str, branch_refs: list[str],
          max_paths: int = 20_000) -> dict[str, object]:
    root = root.resolve()
    if not branch_refs or len(branch_refs) > 200 or len(set(branch_refs)) != len(branch_refs):
        raise AuditError("provide 1..200 distinct explicit branch refs")
    if type(max_paths) is not int or not 1 <= max_paths <= 200_000:
        raise AuditError("invalid path limit")
    if Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() != root:
        raise AuditError("root must be checked-out Git repository top level")
    main_sha = commit(root, main_ref)
    current = tree(root, main_sha)
    results = []
    for ref in branch_refs:
        if ref == main_ref:
            raise AuditError("cannot compare main with itself")
        branch_sha = commit(root, ref)
        common = git(root, "merge-base", main_sha, branch_sha).decode("ascii").strip()
        if not SHA.fullmatch(common):
            raise AuditError("invalid merge-base SHA")
        old = tree(root, branch_sha)
        changed = git(root, "diff", "--no-ext-diff", "--no-textconv",
                      "--no-renames", "--name-only", "-z", common, branch_sha)
        paths = [p.decode("utf-8", "strict") for p in changed.split(b"\0") if p]
        if len(paths) > max_paths or len(paths) != len(set(paths)):
            raise AuditError("changed-path inventory exceeds limit or contains duplicates")
        rows = []
        counts: Counter[str] = Counter()
        for path in paths:
            tip_entry, main_entry = old.get(path), current.get(path)
            status = (
                "byte_identical" if tip_entry == main_entry
                else "missing_on_main" if tip_entry is not None and main_entry is None
                else "removed_on_branch_present_on_main" if tip_entry is None
                else "different_content_or_mode"
            )
            counts[status] += 1
            rows.append({"path": path, "status": status,
                         "branch_blob": tip_entry[1] if tip_entry else None,
                         "main_blob": main_entry[1] if main_entry else None,
                         "branch_mode": tip_entry[0] if tip_entry else None,
                         "main_mode": main_entry[0] if main_entry else None})
        if commit(root, ref) != branch_sha:
            raise AuditError("branch moved during pinned inspection")
        results.append({"ref": ref, "tip_sha": branch_sha,
                        "merge_base_sha": common, "changed_paths": len(paths),
                        "counts": dict(sorted(counts.items())),
                        "all_changed_paths_byte_identical_to_main": bool(paths) and
                            counts["byte_identical"] == len(paths),
                        "requires_manual_review": any(row["status"] != "byte_identical" for row in rows),
                        "paths": rows})
    if commit(root, main_ref) != main_sha:
        raise AuditError("main moved during pinned inspection")
    return {"schema": "skeleton.branch-content-coverage.v1", "main_ref": main_ref,
            "main_sha": main_sha, "branch_count": len(results),
            "deletion_authorized": False, "merging_authorized": False,
            "caveat": "Byte equality is not equivalent to review, tests, intent, or branch-custody approval.",
            "branches": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--main-ref", default="refs/heads/main")
    parser.add_argument("--branch", action="append", required=True,
                        help="Full refs/heads/... or refs/remotes/origin/...; repeat as needed")
    parser.add_argument("--max-paths", type=int, default=20_000)
    args = parser.parse_args()
    print(json.dumps(audit(args.root, main_ref=args.main_ref,
                           branch_refs=args.branch, max_paths=args.max_paths),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
