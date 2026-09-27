#!/usr/bin/env python3
"""Execute every accountability verifier against one exact repository head."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
MAP = Path("machine/ai_accountability_closure_map.json")


class RunnerError(RuntimeError):
    """The verifier runner configuration is invalid."""


def _load_map(root: Path) -> dict[str, Any]:
    path = root / MAP
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError(f"cannot read {path}") from exc
    if not isinstance(payload, dict):
        raise RunnerError("accountability closure map must be an object")
    return payload


def _safe_script(root: Path, rel: object) -> tuple[str, Path]:
    if not isinstance(rel, str) or not rel.strip():
        raise RunnerError("verifier_script must be a non-empty relative path")
    normalized = rel.strip().replace("\\", "/")
    candidate = (root / normalized).resolve()
    resolved_root = root.resolve()
    if candidate == resolved_root or resolved_root not in candidate.parents:
        raise RunnerError(f"verifier path escapes repository: {normalized}")
    if candidate.suffix != ".py":
        raise RunnerError(f"verifier must be a Python script: {normalized}")
    if not candidate.is_file():
        raise RunnerError(f"verifier script is missing: {normalized}")
    return normalized, candidate


def run_verifiers(root: Path, *, head_sha: str) -> dict[str, Any]:
    head = head_sha.strip()
    if not head:
        raise RunnerError("exact head SHA is required")

    mapping = _load_map(root)
    groups = mapping.get("groups")
    if not isinstance(groups, list) or not groups:
        raise RunnerError("accountability closure map has no groups")

    rules = mapping.get("rules")
    if not isinstance(rules, dict):
        raise RunnerError("accountability closure rules are missing")
    task_count = rules.get("queue_task_count")
    tasks_per_group = rules.get("tasks_per_group")
    if (
        isinstance(task_count, bool)
        or not isinstance(task_count, int)
        or isinstance(tasks_per_group, bool)
        or not isinstance(tasks_per_group, int)
        or task_count <= 0
        or tasks_per_group <= 0
        or task_count % tasks_per_group
    ):
        raise RunnerError("accountability closure cardinality rules are invalid")
    expected_groups = task_count // tasks_per_group
    if len(groups) != expected_groups:
        raise RunnerError(
            f"expected {expected_groups} verifier groups, found {len(groups)}"
        )

    base_env = os.environ.copy()
    base_env["GITHUB_SHA"] = head
    base_env["EVIDENCE_HEAD_SHA"] = head
    base_env["ACCOUNTABILITY_HEAD_SHA"] = head
    base_env["PYTHONPATH"] = str(root.resolve())

    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    for group in groups:
        if not isinstance(group, dict):
            raise RunnerError("accountability group must be an object")
        key = str(group.get("key") or "").strip()
        if not key:
            raise RunnerError("accountability group key is required")
        rel, script = _safe_script(root, group.get("verifier_script"))
        if rel in seen:
            raise RunnerError(f"verifier script is reused by multiple groups: {rel}")
        seen.add(rel)

        try:
            completed = subprocess.run(
                [sys.executable, rel],
                cwd=root,
                env=base_env,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
            returncode = completed.returncode
            stdout = completed.stdout[-4096:]
            stderr = completed.stderr[-4096:]
        except subprocess.TimeoutExpired as exc:
            returncode = 124
            stdout = (exc.stdout or "")[-4096:] if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "")[-4096:] if isinstance(exc.stderr, str) else ""
            stderr = (stderr + "\nverifier timed out").strip()

        digest = hashlib.sha256(script.read_bytes()).hexdigest()
        passed = returncode == 0
        if not passed:
            failures.append(key)
        results.append(
            {
                "key": key,
                "gap_id": group.get("gap_id"),
                "verifier_script": rel,
                "script_digest": digest,
                "returncode": returncode,
                "passed": passed,
                "stdout_tail": stdout,
                "stderr_tail": stderr,
            }
        )

    return {
        "schema_version": 1,
        "verifier": "ai-accountability-verifier-runner-v1",
        "head_sha": head,
        "verifier_count": len(results),
        "passed_count": sum(1 for result in results if result["passed"]),
        "failures": failures,
        "results": results,
        "valid": not failures and len(results) == expected_groups,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--head-sha",
        default=(
            os.environ.get("ACCOUNTABILITY_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
        ),
    )
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = run_verifiers(args.root, head_sha=args.head_sha)
    except RunnerError as exc:
        print(f"AI accountability verifier runner: rejected: {exc}", file=sys.stderr)
        return 2

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print(
            "AI accountability verifier runner: FAIL "
            + ", ".join(receipt["failures"]),
            file=sys.stderr,
        )
        return 1
    print(
        "AI accountability verifier runner: OK "
        f"({receipt['passed_count']}/{receipt['verifier_count']} passed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
