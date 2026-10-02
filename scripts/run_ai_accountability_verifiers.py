#!/usr/bin/env python3
"""Execute every accountability verifier against one exact repository head."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
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


def _read_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunnerError(f"verifier did not emit a readable receipt: {path.name}") from exc
    if not isinstance(payload, dict):
        raise RunnerError(f"verifier receipt must be an object: {path.name}")
    return payload


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

    with tempfile.TemporaryDirectory(prefix="accountability-verifiers-") as tmp:
        receipt_root = Path(tmp)
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                raise RunnerError("accountability group must be an object")
            key = str(group.get("key") or "").strip()
            gap_id = str(group.get("gap_id") or "").strip()
            if not key:
                raise RunnerError("accountability group key is required")
            if not gap_id:
                raise RunnerError(f"{key}: accountability gap_id is required")
            rel, script = _safe_script(root, group.get("verifier_script"))
            expected_receipt_verifier = str(
                group.get("expected_receipt_verifier") or ""
            ).strip()
            if not expected_receipt_verifier:
                raise RunnerError(
                    f"{key}: expected_receipt_verifier is required"
                )
            expected_script_sha256 = str(
                group.get("expected_script_sha256") or ""
            ).strip()
            if not re.fullmatch(r"[0-9a-f]{64}", expected_script_sha256):
                raise RunnerError(
                    f"{key}: expected_script_sha256 must be a SHA-256 digest"
                )
            actual_script_sha256 = hashlib.sha256(script.read_bytes()).hexdigest()
            if actual_script_sha256 != expected_script_sha256:
                raise RunnerError(
                    f"{key}: verifier script digest drift "
                    f"(expected {expected_script_sha256}, found {actual_script_sha256})"
                )
            if rel in seen:
                raise RunnerError(
                    f"verifier script is reused by multiple groups: {rel}"
                )
            seen.add(rel)

            evidence = receipt_root / f"{index:02d}-{key}.json"
            returncode = 0
            stdout = ""
            stderr = ""
            receipt: dict[str, Any] | None = None
            receipt_error: str | None = None

            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        rel,
                        "--evidence-out",
                        str(evidence),
                    ],
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
                stdout = (
                    (exc.stdout or "")[-4096:]
                    if isinstance(exc.stdout, str)
                    else ""
                )
                stderr = (
                    (exc.stderr or "")[-4096:]
                    if isinstance(exc.stderr, str)
                    else ""
                )
                stderr = (stderr + "\nverifier timed out").strip()

            if returncode == 0:
                try:
                    receipt = _read_receipt(evidence)
                except RunnerError as exc:
                    receipt_error = str(exc)
            else:
                receipt_error = f"verifier exited with code {returncode}"

            if receipt is not None:
                if receipt.get("head_sha") != head:
                    receipt_error = "verifier receipt is not exact-head"
                elif receipt.get("verifier") != expected_receipt_verifier:
                    receipt_error = "verifier receipt identity mismatch"
                elif receipt.get("valid") is not True or receipt.get("errors"):
                    receipt_error = "verifier receipt reports invalid evidence"
                elif (
                    receipt.get("gap_id") is not None
                    and receipt.get("gap_id") != gap_id
                ):
                    receipt_error = "verifier receipt gap binding mismatch"

            passed = returncode == 0 and receipt is not None and receipt_error is None
            if not passed:
                failures.append(key)

            result: dict[str, Any] = {
                "key": key,
                "gap_id": gap_id,
                "verifier_script": rel,
                "expected_receipt_verifier": expected_receipt_verifier,
                "expected_script_sha256": expected_script_sha256,
                "script_digest": actual_script_sha256,
                "returncode": returncode,
                "passed": passed,
                "stdout_tail": stdout,
                "stderr_tail": stderr,
                "receipt_error": receipt_error,
            }
            if receipt is not None:
                result.update(
                    {
                        "receipt_verifier": receipt.get("verifier"),
                        "receipt_head_sha": receipt.get("head_sha"),
                        "receipt_valid": receipt.get("valid"),
                        "receipt_digest": hashlib.sha256(
                            evidence.read_bytes()
                        ).hexdigest(),
                    }
                )
            results.append(result)

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
