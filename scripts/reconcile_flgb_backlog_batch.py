#!/usr/bin/env python3
"""Read-only, exact-HEAD reconciliation of the functional LLM game-builder backlog.

This audits declared file targets, not semantics, execution, quality or signoffs.
It never edits the authoritative task backlog and never creates CI workflows.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Any

BACKLOG = "machine/functional_llm_game_builder_execution_backlog.json"
TARGET_FIELDS = ("implementation_target", "contract_target", "test_target")


def git_snapshot(root: Path) -> tuple[str, set[str]]:
    """Obtain a complete tracked-file listing, not a truncated GitHub API tree."""
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    listing = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-rz", "--name-only", "HEAD"],
        capture_output=True, check=True,
    ).stdout
    return head, {p.decode("utf-8") for p in listing.split(b"\0") if p}


def _valid_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def reconcile(
    manifest: dict[str, Any],
    tracked: set[str],
    head: str,
    *,
    start: int = 0,
    count: int = 100,
) -> dict[str, Any]:
    """Inspect a fixed deterministic slice; reject malformed manifests."""
    tasks = manifest.get("tasks")
    planes = manifest.get("planes")
    if not isinstance(tasks, list) or not isinstance(planes, list):
        raise ValueError("backlog tasks and planes must be lists")
    if manifest.get("task_count") != len(tasks):
        raise ValueError("declared backlog task_count differs from task entries")
    if manifest.get("plane_count") != len(planes):
        raise ValueError("declared plane_count differs from plane entries")
    if not isinstance(start, int) or not isinstance(count, int):
        raise ValueError("start and count must be integers")
    if start < 0 or count < 1 or start + count > len(tasks):
        raise ValueError("requested slice exceeds the bounded backlog")
    if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise ValueError("the review must be pinned to a full lowercase SHA")

    plane_by_id = {p["id"]: p for p in planes}
    if len(plane_by_id) != len(planes):
        raise ValueError("duplicate plane IDs")
    task_ids = [t["id"] for t in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("duplicate task IDs")
    if set(task_ids) != {i for p in planes for i in p["task_ids"]}:
        raise ValueError("plane membership does not match task roster")

    results: list[dict[str, Any]] = []
    for task in tasks[start:start + count]:
        task_id = task["id"]
        plane_id = task["plane_id"]
        if plane_id not in plane_by_id or task_id not in plane_by_id[plane_id]["task_ids"]:
            raise ValueError(f"{task_id}: unknown or inconsistent plane")
        fields = {key: task.get(key) for key in TARGET_FIELDS}
        if not all(_valid_path(p) for p in fields.values()):
            raise ValueError(f"{task_id}: unsafe or missing path declaration")
        present = {key: path in tracked for key, path in fields.items()}
        missing = [key for key in TARGET_FIELDS if not present[key]]
        state = task.get("state")
        signed = bool(task.get("implementation_signed"))
        independently_signed = bool(task.get("independent_verification_signed"))
        results.append({
            "id": task_id,
            "plane_id": plane_id,
            "subsystem": task.get("subsystem"),
            "declared_state": state,
            "implementation_target": fields["implementation_target"],
            "contract_target": fields["contract_target"],
            "test_target": fields["test_target"],
            "implementation_file_present": present["implementation_target"],
            "contract_file_present": present["contract_target"],
            "test_file_present": present["test_target"],
            "missing_target_types": missing,
            "implementation_signed": signed,
            "independent_verification_signed": independently_signed,
            "review_result": (
                "missing-declared-files" if missing
                else "files-present-not-verified"
            ),
        })
    counts: dict[str, int] = {}
    for item in results:
        counts[item["declared_state"]] = counts.get(item["declared_state"], 0) + 1
    return {
        "schema": "skeleton.flgb.backlog-reconciliation.v1",
        "backlog_path": BACKLOG,
        "source_sha": head,
        "start": start,
        "count": count,
        "total_backlog_tasks": len(tasks),
        "api_tree_truncation_assumed": False,
        "reviewed_task_count": len(results),
        "all_three_files_present": sum(not r["missing_target_types"] for r in results),
        "missing_any_declared_target": sum(bool(r["missing_target_types"]) for r in results),
        "declared_state_counts": dict(sorted(counts.items())),
        "all_tasks_independently_verified": all(r["independent_verification_signed"] for r in results),
        "completion_claim": False,
        "scope_note": "File existence only; no tests executed, no model training or E2E verified.",
        "items": results,
    }


def as_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Functional LLM Game Builder — pinned backlog reconciliation",
        "",
        f"- HEAD: \`{report['source_sha']}\`",
        f"- Slice: [{report['start']}, {report['start'] + report['count']})",
        f"- Files present (all three declared paths): {report['all_three_files_present']}/{report['count']}",
        f"- Declared files missing: {report['missing_any_declared_target']}",
        "- All statuses are manifest claims; this does not run tests or sign work.",
        "",
        "| Task | Subsystem | Impl | Contract | Test | Manifest state |",
        "| --- | --- | :---: | :---: | :---: | --- |",
    ]
    for item in report["items"]:
        safe_subsystem = str(item["subsystem"]).replace("|", "/")
        checks = [
            "yes" if item[field] else "no"
            for field in ("implementation_file_present", "contract_file_present", "test_file_present")
        ]
        lines.append(
            f"| {item['id']} | {safe_subsystem} | "
            f"{checks[0]} | {checks[1]} | {checks[2]} | "
            f"{item['declared_state']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    # Bind the manifest to the same commit as the tracked-file inventory.
    # Reading the working copy could silently mix dirty draft edits with HEAD.
    head, paths = git_snapshot(args.repo)
    manifest_bytes = subprocess.run(
        ["git", "-C", str(args.repo), "show", f"{head}:{BACKLOG}"],
        capture_output=True, check=True,
    ).stdout
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    report = reconcile(manifest, paths, head, start=args.start, count=args.count)
    if args.format == "markdown":
        print(as_markdown(report))
    else:
        print(json.dumps(report, sort_keys=True, indent=2))
    return 1 if report["missing_any_declared_target"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
