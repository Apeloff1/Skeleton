#!/usr/bin/env python3
"""Verify terminal completion of the canonical 42-task P0 accountability queue.

This verifier is intentionally stricter than the phase-inheritance verifier:
terminal P0/P1/P2 claims may remain historically valid when construction ledgers
are reopened, but a *42/42 P0 accountability closure* claim is valid only while
all queue/ledger records remain complete and fresh exact-head independent
verifier receipts prove every mapped gap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
QUEUE = Path("machine/ai_build_queue.json")
LEDGER = Path("machine/ai_build_accountability.json")
CLOSURE_MAP = Path("machine/ai_accountability_closure_map.json")

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


class TerminalAccountabilityError(RuntimeError):
    """Terminal accountability evidence is malformed or unreadable."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalAccountabilityError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise TerminalAccountabilityError(f"{path} must contain an object")
    return value


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _head(explicit: str | None) -> str:
    value = (
        (explicit or "").strip()
        or os.environ.get("ACCOUNTABILITY_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
    )
    if not SHA40_RE.fullmatch(value):
        raise TerminalAccountabilityError("exact 40-character head SHA is required")
    return value


def _groups(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    raw = mapping.get("groups")
    if not isinstance(raw, list):
        raise TerminalAccountabilityError("closure map groups must be a list")
    groups = [item for item in raw if isinstance(item, dict)]
    if len(groups) != len(raw):
        raise TerminalAccountabilityError("closure map groups must be objects")
    return groups


def verify_terminal(
    root: Path = ROOT,
    *,
    head_sha: str | None,
    verifier_receipt: Path,
    closure_map_receipt: Path,
) -> dict[str, Any]:
    head = _head(head_sha)
    queue_path = root / QUEUE
    ledger_path = root / LEDGER
    map_path = root / CLOSURE_MAP
    queue = _load(queue_path)
    ledger = _load(ledger_path)
    mapping = _load(map_path)
    runner = _load(verifier_receipt)
    bridge = _load(closure_map_receipt)

    errors: list[str] = []
    current_digests = {
        "build_queue": _digest(queue_path),
        "accountability_ledger": _digest(ledger_path),
        "closure_map": _digest(map_path),
    }
    tasks = queue.get("tasks")
    records = ledger.get("records")
    groups = _groups(mapping)

    if not isinstance(tasks, list):
        tasks = []
        errors.append("build queue tasks must be a list")
    if not isinstance(records, list):
        records = []
        errors.append("accountability records must be a list")

    expected_count = mapping.get("rules", {}).get("queue_task_count")
    if expected_count != 42:
        errors.append("closure map queue_task_count must remain exactly 42")
    if len(tasks) != 42:
        errors.append(f"terminal P0 queue must contain 42 tasks; found {len(tasks)}")
    if len(groups) != 14:
        errors.append(f"terminal P0 closure map must contain 14 groups; found {len(groups)}")

    record_by_id = {
        str(record.get("id")): record
        for record in records
        if isinstance(record, dict)
    }

    group_by_task: dict[str, dict[str, Any]] = {}
    for group in groups:
        prefix = str(group.get("task_prefix") or "")
        if not prefix:
            errors.append("closure-map group has empty task_prefix")
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("task_id") or "")
            if task_id.startswith(prefix):
                if task_id in group_by_task:
                    errors.append(f"{task_id}: mapped by more than one closure group")
                group_by_task[task_id] = group

    terminal_count = 0
    bridge_signed_count = 0
    for task in tasks:
        if not isinstance(task, dict):
            errors.append("queue task must be an object")
            continue
        task_id = str(task.get("task_id") or "")
        accountability_id = str(task.get("accountability_id") or "")
        expected_id = f"ACC-{task_id}"
        if accountability_id != expected_id:
            errors.append(f"{task_id}: accountability_id must be {expected_id}")
        group = group_by_task.get(task_id)
        if group is None:
            errors.append(f"{task_id}: no terminal closure group mapping")

        if task.get("status") != "done":
            errors.append(f"{task_id}: queue status is not done")
        if task.get("completion_checkbox") is not True:
            errors.append(f"{task_id}: queue completion checkbox is not checked")
        if task.get("completion_checkbox_mark") != "[x]":
            errors.append(f"{task_id}: queue completion mark is not [x]")
        if task.get("implementation_signed") is not True:
            errors.append(f"{task_id}: queue implementation signoff is not present")
        if task.get("verification_signed") is not True:
            errors.append(f"{task_id}: queue verification signoff is not present")

        record = record_by_id.get(accountability_id)
        if record is None:
            errors.append(f"{task_id}: missing accountability record {accountability_id}")
            continue
        if record.get("type") != "queue_task":
            errors.append(f"{accountability_id}: ledger record type must be queue_task")
        if record.get("status") != "done":
            errors.append(f"{accountability_id}: ledger status is not done")
        if record.get("checkbox") is not True or record.get("checkbox_mark") != "[x]":
            errors.append(f"{accountability_id}: ledger completion checkbox is not terminal")

        impl = record.get("implementation_signoff")
        verify = record.get("verification_signoff")
        impl_signed = isinstance(impl, dict) and impl.get("signed") is True
        verify_signed = isinstance(verify, dict) and verify.get("signed") is True
        if not impl_signed:
            errors.append(f"{accountability_id}: ledger implementation signoff missing")
        if not verify_signed:
            errors.append(f"{accountability_id}: ledger verification signoff missing")
        if impl_signed and verify_signed and impl.get("signer_id") == verify.get("signer_id"):
            errors.append(f"{accountability_id}: implementation and verification signer must differ")

        history = record.get("history")
        if not isinstance(history, list) or not history:
            errors.append(f"{accountability_id}: terminal record needs history")
        else:
            last = history[-1]
            if not isinstance(last, dict):
                errors.append(f"{accountability_id}: final history event must be an object")
            else:
                if last.get("event_type") != "completed":
                    errors.append(f"{accountability_id}: final history event is not completed")
                if last.get("to_status") != "done":
                    errors.append(f"{accountability_id}: final history event does not end at done")

        if not isinstance(record.get("completed_at_utc"), str) or not record["completed_at_utc"]:
            errors.append(f"{accountability_id}: completed_at_utc is missing")
        evidence = record.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{accountability_id}: terminal evidence is missing")

        if isinstance(verify, dict) and verify.get("signer_id") == "github-actions:AI Accountability Closure Bridge":
            bridge_signed_count += 1
            verifier_script = str((group or {}).get("verifier_script") or "")
            refs = set(str(item) for item in verify.get("evidence_refs", []) if isinstance(item, str))
            all_refs = set(str(item) for item in evidence or [] if isinstance(item, str))
            if not verifier_script:
                errors.append(f"{accountability_id}: mapped verifier script is missing")
            elif verifier_script not in refs or verifier_script not in all_refs:
                errors.append(
                    f"{accountability_id}: bridge signoff does not bind mapped verifier {verifier_script}"
                )
            signature_ref = str(verify.get("signature_ref") or "")
            if "/actions/runs/" not in signature_ref:
                errors.append(f"{accountability_id}: bridge verification signature_ref is not a workflow run")

        if (
            task.get("status") == "done"
            and task.get("completion_checkbox") is True
            and task.get("implementation_signed") is True
            and task.get("verification_signed") is True
            and record.get("status") == "done"
            and record.get("checkbox") is True
            and impl_signed
            and verify_signed
        ):
            terminal_count += 1

    if len(group_by_task) != len(tasks):
        errors.append(
            f"terminal group coverage mismatch: mapped {len(group_by_task)} of {len(tasks)} queue tasks"
        )

    expected_candidate_counts = {
        "implementation_ready": 0,
        "verification_ready": 0,
        "completion_ready": 0,
        "done": 42,
    }
    if bridge.get("head_sha") != head:
        errors.append("closure-map receipt is not exact-head")
    if bridge.get("verifier") != "ai-accountability-closure-map-v1":
        errors.append("unexpected closure-map receipt verifier")
    if bridge.get("valid") is not True or bridge.get("errors"):
        errors.append("closure-map receipt is invalid")
    if bridge.get("task_count") != 42 or bridge.get("mapped_task_count") != 42:
        errors.append("closure-map receipt does not cover all 42 tasks")
    if bridge.get("group_count") != 14:
        errors.append("closure-map receipt does not cover all 14 groups")
    if bridge.get("candidate_counts") != expected_candidate_counts:
        errors.append("closure-map receipt is not terminal 42/42 done")
    bridge_digests = bridge.get("digests")
    if not isinstance(bridge_digests, dict):
        errors.append("closure-map receipt digests are missing")
    else:
        for name, expected_digest in current_digests.items():
            if bridge_digests.get(name) != expected_digest:
                errors.append(
                    f"closure-map receipt {name} digest does not match current repository"
                )

    if runner.get("head_sha") != head:
        errors.append("verifier-runner receipt is not exact-head")
    if runner.get("verifier") != "ai-accountability-verifier-runner-v1":
        errors.append("unexpected verifier-runner receipt verifier")
    if runner.get("valid") is not True or runner.get("failures"):
        errors.append("verifier-runner receipt is invalid")
    if runner.get("verifier_count") != 14 or runner.get("passed_count") != 14:
        errors.append("verifier-runner did not pass all 14 groups")

    expected_pairs = {
        (str(group.get("key") or ""), str(group.get("gap_id") or ""))
        for group in groups
    }
    results = runner.get("results")
    if not isinstance(results, list):
        results = []
        errors.append("verifier-runner results must be a list")
    actual_pairs = {
        (str(result.get("key") or ""), str(result.get("gap_id") or ""))
        for result in results
        if isinstance(result, dict)
    }
    if actual_pairs != expected_pairs:
        errors.append("verifier-runner group/gap inventory disagrees with closure map")
    for result in results:
        if not isinstance(result, dict):
            errors.append("verifier-runner result must be an object")
            continue
        key = str(result.get("key") or "")
        group = next(
            (item for item in groups if str(item.get("key") or "") == key),
            None,
        )
        expected_receipt_verifier = str(
            (group or {}).get("expected_receipt_verifier") or ""
        )
        expected_script_sha256 = str(
            (group or {}).get("expected_script_sha256") or ""
        )
        if result.get("passed") is not True:
            errors.append(f"{key}: fresh independent verifier did not pass")
        if not expected_receipt_verifier:
            errors.append(f"{key}: expected receipt verifier is missing")
        elif result.get("receipt_verifier") != expected_receipt_verifier:
            errors.append(f"{key}: fresh verifier receipt identity mismatch")
        if not expected_script_sha256:
            errors.append(f"{key}: expected verifier script digest is missing")
        elif result.get("script_digest") != expected_script_sha256:
            errors.append(f"{key}: fresh verifier script digest mismatch")
        if result.get("receipt_head_sha") != head:
            errors.append(f"{result.get('key')}: child verifier receipt is not exact-head")
        if not result.get("receipt_digest"):
            errors.append(f"{result.get('key')}: child verifier receipt digest is missing")

    return {
        "schema_version": 1,
        "verifier": "ai-p0-accountability-terminal-v1",
        "head_sha": head,
        "valid": not errors,
        "errors": errors,
        "task_count": len(tasks),
        "terminal_task_count": terminal_count,
        "group_count": len(groups),
        "fresh_verifier_pass_count": int(runner.get("passed_count") or 0),
        "bridge_signed_task_count": bridge_signed_count,
        "digests": {
            **current_digests,
            "verifier_runner_receipt": _digest(verifier_receipt),
            "closure_map_receipt": _digest(closure_map_receipt),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--head-sha")
    parser.add_argument("--verifier-receipt", type=Path, required=True)
    parser.add_argument("--closure-map-receipt", type=Path, required=True)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_terminal(
            args.root,
            head_sha=args.head_sha,
            verifier_receipt=args.verifier_receipt,
            closure_map_receipt=args.closure_map_receipt,
        )
    except TerminalAccountabilityError as exc:
        print(f"AI P0 accountability terminal verifier: rejected: {exc}", file=sys.stderr)
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
        print("AI P0 accountability terminal verifier: FAIL", file=sys.stderr)
        for error in receipt["errors"]:
            print(f" - {error}", file=sys.stderr)
        return 1

    print(
        "AI P0 accountability terminal verifier: OK "
        f"({receipt['terminal_task_count']}/{receipt['task_count']} done; "
        f"{receipt['fresh_verifier_pass_count']}/{receipt['group_count']} fresh verifiers)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
