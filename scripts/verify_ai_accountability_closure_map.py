#!/usr/bin/env python3
"""Independently validate the atomic AI accountability closure bridge.

The bridge is deliberately non-mutating. It proves that every atomic build
queue task maps to exactly one closed canonical gap and an independent
exact-head verification gate before a separate signed lifecycle action may
advance the accountability ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "machine" / "ai_accountability_closure_map.json"
QUEUE = ROOT / "machine" / "ai_build_queue.json"
LEDGER = ROOT / "machine" / "ai_build_accountability.json"
CONSTRUCTION = ROOT / "machine" / "ai_app_construction.json"
HANDOFF = ROOT / "machine" / "ai_implementation_handoff.json"
CLOSURE = ROOT / "machine" / "ai_closure_evidence.json"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BridgeVerificationError(RuntimeError):
    """The accountability closure bridge is malformed."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeVerificationError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise BridgeVerificationError(f"{path} must contain an object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _entry(items: object, key: str, value: str) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get(key) == value:
            return item
    return None


def _workflow_exact_head_errors(
    root: Path,
    workflow_rel: str,
    expected_name: str,
) -> list[str]:
    errors: list[str] = []
    path = root / workflow_rel
    if not path.is_file():
        return [f"missing verification workflow: {workflow_rel}"]
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^name:\s*(.+?)\s*$", text, re.MULTILINE)
    actual_name = match.group(1).strip() if match else ""
    if actual_name != expected_name:
        errors.append(
            f"{workflow_rel}: workflow name mismatch "
            f"(expected {expected_name!r}, found {actual_name!r})"
        )
    if "pull_request:" not in text:
        errors.append(f"{workflow_rel}: verification gate must run on pull_request")
    if "actions/checkout@" not in text:
        errors.append(f"{workflow_rel}: verification gate must check out repository")
    if "github.event.pull_request.head.sha" not in text:
        errors.append(
            f"{workflow_rel}: verification gate must bind checkout/evidence to exact PR head"
        )
    if not re.search(
        r"ref:\s*\$\{\{[^\n]*github\.event\.pull_request\.head\.sha",
        text,
    ):
        errors.append(
            f"{workflow_rel}: checkout ref must explicitly use pull_request.head.sha"
        )
    return errors


def _candidate_state(record: dict[str, Any]) -> str:
    impl = record.get("implementation_signoff")
    verify = record.get("verification_signoff")
    impl_signed = isinstance(impl, dict) and impl.get("signed") is True
    verify_signed = isinstance(verify, dict) and verify.get("signed") is True
    checked = record.get("checkbox") is True
    status = str(record.get("status") or "").lower()

    if checked and status == "done" and impl_signed and verify_signed:
        return "done"
    if impl_signed and verify_signed:
        return "completion_ready"
    if impl_signed:
        return "verification_ready"
    return "implementation_ready"


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    mapping = _load(root / MAP.relative_to(ROOT))
    queue = _load(root / QUEUE.relative_to(ROOT))
    ledger = _load(root / LEDGER.relative_to(ROOT))
    construction = _load(root / CONSTRUCTION.relative_to(ROOT))
    handoff = _load(root / HANDOFF.relative_to(ROOT))
    closure = _load(root / CLOSURE.relative_to(ROOT))

    groups = mapping.get("groups")
    tasks = queue.get("tasks")
    records = ledger.get("records")
    gaps = construction.get("gap_register")
    handoff_entries = handoff.get("entries")
    closure_entries = closure.get("entries")

    if mapping.get("schema_version") != 1:
        errors.append("closure map schema_version must equal 1")
    if mapping.get("status") != "active":
        errors.append("closure map status must be active")
    if not isinstance(groups, list):
        errors.append("closure map groups must be a list")
        groups = []
    if not isinstance(tasks, list):
        errors.append("build queue tasks must be a list")
        tasks = []
    if not isinstance(records, list):
        errors.append("accountability records must be a list")
        records = []

    expected_task_count = (
        mapping.get("rules", {}).get("queue_task_count")
        if isinstance(mapping.get("rules"), dict)
        else None
    )
    if expected_task_count != len(tasks):
        errors.append(
            f"queue task count mismatch: expected {expected_task_count}, found {len(tasks)}"
        )

    group_keys: set[str] = set()
    prefixes: set[str] = set()
    gap_ids: set[str] = set()
    task_to_group: dict[str, dict[str, Any]] = {}
    group_summaries: list[dict[str, Any]] = []

    for group in groups:
        if not isinstance(group, dict):
            errors.append("closure map group must be an object")
            continue
        key = str(group.get("key") or "")
        prefix = str(group.get("task_prefix") or "")
        gap_id = str(group.get("gap_id") or "")
        workflow = str(group.get("workflow") or "")
        workflow_name = str(group.get("workflow_name") or "")
        verifier_script = group.get("verifier_script")
        stage = group.get("stage")

        if not key or key in group_keys:
            errors.append(f"duplicate/empty group key: {key!r}")
        group_keys.add(key)
        if not prefix or prefix in prefixes:
            errors.append(f"duplicate/empty task prefix: {prefix!r}")
        prefixes.add(prefix)
        if not gap_id or gap_id in gap_ids:
            errors.append(f"duplicate/empty gap id: {gap_id!r}")
        gap_ids.add(gap_id)
        if isinstance(stage, bool) or not isinstance(stage, int) or not 0 <= stage <= 7:
            errors.append(f"{key}: invalid stage {stage!r}")

        gap = _entry(gaps, "id", gap_id)
        hand = _entry(handoff_entries, "gap", gap_id)
        close = _entry(closure_entries, "gap", gap_id)
        if gap is None:
            errors.append(f"{key}: missing construction gap {gap_id}")
        elif gap.get("status") != "closed":
            errors.append(f"{key}: construction gap {gap_id} is not closed")
        if hand is None:
            errors.append(f"{key}: missing handoff {gap_id}")
        elif hand.get("implementation_status") != "closed":
            errors.append(f"{key}: handoff {gap_id} is not closed")
        if close is None:
            errors.append(f"{key}: missing closure evidence {gap_id}")
        else:
            if close.get("gap_status") != "closed":
                errors.append(f"{key}: closure gap_status for {gap_id} is not closed")
            if close.get("implementation_state") != "closed":
                errors.append(
                    f"{key}: closure implementation_state for {gap_id} is not closed"
                )
            if close.get("closure_decision") != "closed":
                errors.append(
                    f"{key}: closure decision for {gap_id} is not closed"
                )
            evidence = close.get("evidence_present")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"{key}: closure evidence for {gap_id} is empty")
            if close.get("outstanding_evidence") not in ([], None):
                errors.append(f"{key}: {gap_id} still has outstanding evidence")
            if close.get("blockers") not in ([], None):
                errors.append(f"{key}: {gap_id} still has blockers")

        errors.extend(
            _workflow_exact_head_errors(root, workflow, workflow_name)
        )
        if not isinstance(verifier_script, str) or not verifier_script:
            errors.append(f"{key}: verifier_script is required")
        else:
            verifier_path = root / verifier_script
            if not verifier_path.is_file():
                errors.append(
                    f"{key}: missing verifier script {verifier_script}"
                )
            else:
                source = verifier_path.read_text(encoding="utf-8")
                binding_token = str(
                    group.get("verifier_binding_token") or gap_id
                )
                if binding_token not in source:
                    errors.append(
                        f"{key}: verifier {verifier_script} does not bind "
                        f"{binding_token}"
                    )
                workflow_path = root / workflow
                if workflow_path.is_file():
                    workflow_source = workflow_path.read_text(encoding="utf-8")
                    verifier_exec = re.compile(
                        r"(?m)^\\s*(?:python|python3)\\s+"
                        + re.escape(verifier_script)
                        + r"(?:\\s|$)"
                    )
                    if verifier_exec.search(workflow_source) is None:
                        errors.append(
                            f"{key}: workflow {workflow} does not execute "
                            f"{verifier_script}"
                        )
                    verifier_trigger = re.compile(
                        r"(?m)^\\s*-\\s*[\"']?"
                        + re.escape(verifier_script)
                        + r"[\"']?\\s*$"
                    )
                    if verifier_trigger.search(workflow_source) is None:
                        errors.append(
                            f"{key}: workflow {workflow} does not trigger on "
                            f"{verifier_script}"
                        )

        matching = [
            task
            for task in tasks
            if isinstance(task, dict)
            and str(task.get("task_id") or "").startswith(prefix)
        ]
        expected_per_group = mapping.get("rules", {}).get("tasks_per_group", 3)
        if len(matching) != expected_per_group:
            errors.append(
                f"{key}: expected {expected_per_group} tasks for {prefix}, "
                f"found {len(matching)}"
            )
        for task in matching:
            task_id = str(task.get("task_id") or "")
            if task_id in task_to_group:
                errors.append(
                    f"{task_id}: mapped by multiple groups "
                    f"{task_to_group[task_id].get('key')} and {key}"
                )
            task_to_group[task_id] = group
            if task.get("stage") != stage:
                errors.append(
                    f"{task_id}: queue stage {task.get('stage')} disagrees with {key}"
                )
            expected_acc = "ACC-" + task_id
            if task.get("accountability_id") != expected_acc:
                errors.append(
                    f"{task_id}: accountability_id must be {expected_acc}"
                )
        group_summaries.append(
            {
                "key": key,
                "stage": stage,
                "gap_id": gap_id,
                "task_count": len(matching),
                "workflow": workflow,
                "workflow_name": workflow_name,
                "verifier_script": verifier_script,
                "verifier_binding_token": (
                    group.get("verifier_binding_token") or gap_id
                ),
            }
        )

    task_ids = [
        str(task.get("task_id") or "")
        for task in tasks
        if isinstance(task, dict)
    ]
    unmapped = sorted(set(task_ids) - set(task_to_group))
    if unmapped:
        errors.append("unmapped queue tasks: " + ", ".join(unmapped))
    extra = sorted(set(task_to_group) - set(task_ids))
    if extra:
        errors.append("mapping references unknown queue tasks: " + ", ".join(extra))

    record_by_id = {
        str(record.get("id")): record
        for record in records
        if isinstance(record, dict)
    }
    candidate_counts = {
        "implementation_ready": 0,
        "verification_ready": 0,
        "completion_ready": 0,
        "done": 0,
    }
    candidates: list[dict[str, Any]] = []

    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id") or "")
        accountability_id = str(task.get("accountability_id") or "")
        record = record_by_id.get(accountability_id)
        if record is None:
            errors.append(f"{task_id}: missing ledger record {accountability_id}")
            continue
        if record.get("type") != "queue_task":
            errors.append(
                f"{accountability_id}: ledger record type must be queue_task"
            )
        title = str(record.get("title") or "")
        if task_id not in title:
            errors.append(f"{accountability_id}: title does not bind queue task id")
        if record.get("id") != "ACC-" + task_id:
            errors.append(f"{task_id}: ledger id mismatch")

        impl = record.get("implementation_signoff")
        verify = record.get("verification_signoff")
        impl_signed = isinstance(impl, dict) and impl.get("signed") is True
        verify_signed = isinstance(verify, dict) and verify.get("signed") is True
        if verify_signed and not impl_signed:
            errors.append(
                f"{accountability_id}: verification cannot precede implementation"
            )
        if (
            impl_signed
            and verify_signed
            and impl.get("signer_id") == verify.get("signer_id")
            and not isinstance(record.get("independence_exception"), dict)
        ):
            errors.append(
                f"{accountability_id}: same-signer verification lacks exception"
            )

        state = _candidate_state(record)
        candidate_counts[state] += 1
        group = task_to_group.get(task_id, {})
        candidates.append(
            {
                "task_id": task_id,
                "accountability_id": accountability_id,
                "candidate_state": state,
                "gap_id": group.get("gap_id"),
                "workflow_name": group.get("workflow_name"),
                "implementation_signed": impl_signed,
                "verification_signed": verify_signed,
                "checkbox": record.get("checkbox") is True,
            }
        )

    digests = {
        "closure_map": _digest(root / MAP.relative_to(ROOT)),
        "build_queue": _digest(root / QUEUE.relative_to(ROOT)),
        "accountability_ledger": _digest(root / LEDGER.relative_to(ROOT)),
        "construction": _digest(root / CONSTRUCTION.relative_to(ROOT)),
        "handoff": _digest(root / HANDOFF.relative_to(ROOT)),
        "closure_evidence": _digest(root / CLOSURE.relative_to(ROOT)),
    }
    if not all(SHA256_RE.fullmatch(value) for value in digests.values()):
        errors.append("receipt digest generation failed")

    return {
        "schema_version": 1,
        "verifier": "ai-accountability-closure-map-v1",
        "head_sha": (
            os.environ.get("ACCOUNTABILITY_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "valid": not errors,
        "errors": errors,
        "task_count": len(tasks),
        "group_count": len(groups),
        "mapped_task_count": len(task_to_group),
        "candidate_counts": candidate_counts,
        "groups": group_summaries,
        "candidates": candidates,
        "digests": digests,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(args.root)
    except BridgeVerificationError as exc:
        print(f"AI accountability closure bridge: rejected: {exc}", file=sys.stderr)
        return 1

    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if not receipt["valid"]:
        print("AI accountability closure bridge: FAIL", file=sys.stderr)
        for error in receipt["errors"]:
            print(f" - {error}", file=sys.stderr)
        return 1

    counts = receipt["candidate_counts"]
    print(
        "AI accountability closure bridge: OK "
        f"({receipt['mapped_task_count']}/{receipt['task_count']} mapped; "
        f"{counts['done']} done; "
        f"{counts['completion_ready']} completion-ready; "
        f"{counts['verification_ready']} verification-ready; "
        f"{counts['implementation_ready']} implementation-ready)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
