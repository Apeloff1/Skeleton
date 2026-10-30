"""Fail-closed Git/GitHub size admission for hourly original-studio draft slices.

Apply *before every draft push*, on the exact prospective base/head tree pair.
This gate enforces provider object and upload limits; GitHub UI truncation
produces review advisories rather than arbitrary source-admission rejection. It does not bypass existing security or release checks.

Example:
 python scripts/studio_git_admission.py --base origin/main --head HEAD \
   --repo-size-kib 260000 --open-studio-drafts 8 --remote-branches 900 \
   --pushes-last-minute 1 --json
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import subprocess

# Policy values are conservative *admission* targets, not GitHub hard limits.
# GitHub displays up to 300 changed files / 20k lines / 1MB raw diff; its
# REST PR-files endpoint returns at most 3000 files. Prefer much smaller units.
MAX_CHANGED_FILES = 3_000
MAX_CHANGED_LINES = 2_000_000
MAX_RAW_DIFF_BYTES = 2_000_000_000
MAX_SINGLE_BLOB_BYTES = 100_000_000
MAX_CHANGED_BLOB_BYTES = 2_000_000_000
MAX_DIRECTORY_WIDTH = 100_000
MAX_PATH_DEPTH = 256
RECOMMENDED_REPOSITORY_SIZE_KIB = 5 * 1024 * 1024
RECOMMENDED_DRAFT_BACKLOG = 48
RECOMMENDED_REMOTE_BRANCHES = 5_000
MAX_PUSHES_LAST_MINUTE = 5
PR_UI_VISIBLE_FILES = 300
PR_UI_VISIBLE_LINES = 20_000
PR_UI_VISIBLE_DIFF_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class Change:
    path: str
    additions: int
    deletions: int
    blob_bytes: int
    mode: str = "100644"
    binary: bool = False


@dataclass(frozen=True, slots=True)
class RemoteCapacity:
    repo_size_kib: int
    open_studio_drafts: int
    remote_branches: int
    pushes_last_minute: int


def _integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(name + " must be a non-negative integer")
    return value


def evaluate(
    changes: tuple[Change, ...], capacity: RemoteCapacity, *,
    raw_diff_bytes: int, largest_directory_width: int,
) -> dict[str, object]:
    """Pure admission decision; no omitted/unknown capacity is interpreted as zero."""
    failures: list[str] = []
    if not isinstance(capacity, RemoteCapacity):
        raise ValueError("measured remote capacity is required")
    for name in ("repo_size_kib", "open_studio_drafts", "remote_branches",
                 "pushes_last_minute"):
        _integer(getattr(capacity, name), name)
    _integer(raw_diff_bytes, "raw diff bytes")
    _integer(largest_directory_width, "directory width")
    if len(changes) == 0 or len(changes) > MAX_CHANGED_FILES:
        failures.append("changed_file_count")
    if raw_diff_bytes > MAX_RAW_DIFF_BYTES:
        failures.append("raw_diff_bytes")
    if largest_directory_width > MAX_DIRECTORY_WIDTH:
        failures.append("directory_width")
    advisories: list[str] = []
    if capacity.repo_size_kib >= RECOMMENDED_REPOSITORY_SIZE_KIB:
        advisories.append("repository_size_review")
    if capacity.open_studio_drafts > RECOMMENDED_DRAFT_BACKLOG:
        advisories.append("studio_draft_backlog_review")
    if capacity.remote_branches >= RECOMMENDED_REMOTE_BRANCHES:
        advisories.append("branch_population_review")
    if capacity.pushes_last_minute >= MAX_PUSHES_LAST_MINUTE:
        failures.append("push_rate")
    seen: set[str] = set()
    changed_lines = 0
    blob_total = 0
    max_blob = 0
    for change in changes:
        if not isinstance(change, Change):
            raise ValueError("typed Git change required")
        path = change.path
        parts = PurePosixPath(path).parts if isinstance(path, str) else ()
        if (not parts or path.startswith("/") or "\\" in path
                or path.endswith("/") or path != str(PurePosixPath(path))
                or any(ord(ch) < 32 for ch in path)
                or any(part in (".", "..", ".git") for part in parts)
                or path in seen):
            failures.append("unsafe_or_duplicate_path")
        if len(parts) > MAX_PATH_DEPTH:
            failures.append("path_depth")
        seen.add(path)
        _integer(change.additions, "additions")
        _integer(change.deletions, "deletions")
        _integer(change.blob_bytes, "blob bytes")
        changed_lines += change.additions + change.deletions
        blob_total += change.blob_bytes
        max_blob = max(max_blob, change.blob_bytes)
        if change.mode not in ("100644", "100755") or change.binary:
            failures.append("non_source_blob")
    if changed_lines > MAX_CHANGED_LINES:
        failures.append("changed_lines")
    if max_blob > MAX_SINGLE_BLOB_BYTES:
        failures.append("single_blob_size")
    if blob_total > MAX_CHANGED_BLOB_BYTES:
        failures.append("changed_blob_bytes")
    if len(changes) > PR_UI_VISIBLE_FILES:
        advisories.append("pr_diff_file_visibility")
    if changed_lines > PR_UI_VISIBLE_LINES:
        advisories.append("pr_diff_line_visibility")
    if raw_diff_bytes > PR_UI_VISIBLE_DIFF_BYTES:
        advisories.append("pr_diff_byte_visibility")
    return {
        "schema": "skeleton.game_builder.studio_git_admission.v1",
        "admitted": not failures,
        "violations": sorted(set(failures)),
        "advisories": sorted(set(advisories)),
        "full_review_required": bool(advisories),
        "measured": {
            "changed_files": len(changes),
            "changed_lines": changed_lines,
            "raw_diff_bytes": raw_diff_bytes,
            "max_blob_bytes": max_blob,
            "changed_blob_bytes": blob_total,
            "largest_directory_width": largest_directory_width,
            "repo_size_kib": capacity.repo_size_kib,
            "open_studio_drafts": capacity.open_studio_drafts,
            "remote_branches": capacity.remote_branches,
            "pushes_last_minute": capacity.pushes_last_minute,
        },
        "limits": {
            "changed_files": MAX_CHANGED_FILES,
            "changed_lines": MAX_CHANGED_LINES,
            "raw_diff_bytes": MAX_RAW_DIFF_BYTES,
            "single_blob_bytes": MAX_SINGLE_BLOB_BYTES,
            "changed_blob_bytes": MAX_CHANGED_BLOB_BYTES,
            "directory_width": MAX_DIRECTORY_WIDTH,
            "pushes_last_minute": MAX_PUSHES_LAST_MINUTE,
        },
        "advisory_thresholds": {
            "repository_size_kib": RECOMMENDED_REPOSITORY_SIZE_KIB,
            "studio_drafts": RECOMMENDED_DRAFT_BACKLOG,
            "remote_branches": RECOMMENDED_REMOTE_BRANCHES,
            "pr_visible_files": PR_UI_VISIBLE_FILES,
            "pr_visible_lines": PR_UI_VISIBLE_LINES,
            "pr_visible_diff_bytes": PR_UI_VISIBLE_DIFF_BYTES,
        },
        "action": "push_draft" if not failures else "split_or_reconcile_without_pushing",
        "release_certified": False,
    }


def _git(*argv: str) -> bytes:
    result = subprocess.run(
        ["git", *argv], check=False, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=90,
    )
    if result.returncode != 0:
        raise ValueError("Git inspection failed: " + repr(argv[:2]))
    return result.stdout


def _raw_diff_length(base: str, head: str) -> int:
    process = subprocess.Popen(
        ["git", "diff", "--binary", "--no-ext-diff", "--no-renames",
         base, head, "--"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    total = 0
    with process.stdout:
        while True:
            block = process.stdout.read(65_536)
            if not block:
                break
            total += len(block)
            if total > MAX_RAW_DIFF_BYTES:
                process.kill()
                process.communicate()
                return total  # over-cap result fails closed; no need to read gigabytes
    stderr = process.stderr.read(4_096) if process.stderr else b""
    if process.wait() != 0:
        raise ValueError("Git diff failed: " + repr(stderr[:80]))
    return total


def _changed_paths(base: str, head: str) -> tuple[tuple[str, int, int, bool], ...]:
    raw = _git("diff", "--numstat", "--no-renames", "-z", base, head, "--")
    rows: list[tuple[str, int, int, bool]] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        parts = item.split(b"\t", 2)
        if len(parts) != 3:
            raise ValueError("unsupported Git numstat encoding")
        try:
            path = parts[2].decode("utf-8", "strict")
            binary = parts[0] == b"-" or parts[1] == b"-"
            additions = 0 if binary else int(parts[0])
            deletions = 0 if binary else int(parts[1])
        except (UnicodeError, ValueError) as exc:
            raise ValueError("ambiguous Git change entry") from exc
        rows.append((path, additions, deletions, binary))
        if len(rows) > MAX_CHANGED_FILES:
            break  # already inadmissible; do not follow expensive huge diffs
    return tuple(rows)


def inspect(base: str, head: str, capacity: RemoteCapacity) -> dict[str, object]:
    rows = _changed_paths(base, head)
    paths = [row[0] for row in rows]
    # Query exact resulting Git tree. Deleted paths carry zero new bytes.
    # No shell expansion: even spaces / untrusted names cannot become commands.
    objects: dict[str, tuple[str, int]] = {}
    if paths:
        raw = _git("ls-tree", "-r", "-z", "-l", head, "--", *paths)
        for line in raw.split(b"\0"):
            if not line:
                continue
            try:
                meta, pathname = line.split(b"\t", 1)
                mode, kind, _sha, size = meta.decode("ascii").split()
                objects[pathname.decode("utf-8", "strict")] = (
                    mode if kind == "blob" else "unsupported",
                    int(size) if size.isdigit() else MAX_SINGLE_BLOB_BYTES + 1,
                )
            except (ValueError, UnicodeError) as exc:
                raise ValueError("unsupported Git tree object") from exc
    changes = tuple(Change(path, adds, dels, *objects.get(
        path, ("100644", 0)), binary=binary)
        for path, adds, dels, binary in rows)
    # Directory fanout should be checked on parent tree objects; a failure in
    # any parent (including root) requires splitting/restructuring, not waiver.
    parents = {"/".join(path.split("/")[:k])
               for path in paths for k in range(0, len(path.split("/")))}
    widest = 0
    for parent in sorted(parents):
        try:
            treeish = head if not parent else head + ":" + parent
            blob = _git("ls-tree", "-z", treeish)
        except ValueError:
            continue  # parent was removed; resulting tree has no entries
        widest = max(widest, blob.count(b"\0"))
        if widest > MAX_DIRECTORY_WIDTH:
            break
    return evaluate(
        changes, capacity, raw_diff_bytes=_raw_diff_length(base, head),
        largest_directory_width=widest,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--repo-size-kib", type=int, required=True,
                        help="Fresh GitHub repository.size reading in KiB")
    parser.add_argument("--open-studio-drafts", type=int, required=True,
                        help="Projected draft count AFTER the proposed admission; include +1 for a new draft")
    parser.add_argument("--remote-branches", type=int, required=True)
    parser.add_argument("--pushes-last-minute", type=int, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        capacity = RemoteCapacity(args.repo_size_kib, args.open_studio_drafts,
                                  args.remote_branches, args.pushes_last_minute)
        result = inspect(args.base, args.head, capacity)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        result = {
            "schema": "skeleton.game_builder.studio_git_admission.v1",
            "admitted": False, "violations": ["unverified_git_or_capacity"],
            "error": str(exc)[:240], "action": "stop_push_and_reconcile",
            "release_certified": False,
        }
    print(json.dumps(result, sort_keys=True) if args.json
          else json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["admitted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
