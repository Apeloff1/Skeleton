#!/usr/bin/env python3
"""Verify that P0, P1 and P2 closure authorities still agree on one exact head.

This verifier is deliberately phase-oriented.  It does not reinterpret the
atomic accountability queue as terminal phase authority; instead it proves that
the canonical closure manifests form an intact inheritance chain and that none
of their bounded claims have drifted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]

P0_GAPS = {
    "gap-cognitive-execution-loop",
    "gap-context-compiler-convergence",
    "gap-conversation-state-authority",
    "gap-cost-admission",
    "gap-e2e-golden-journeys",
    "gap-engine-application-execution-boundary",
    "gap-governance-registry",
    "gap-memory-durable-authority",
    "gap-provider-interaction-protocol",
    "gap-provider-surface-convergence",
    "gap-state-authority-convergence",
    "gap-streaming-protocol",
    "gap-tool-runtime-convergence",
    "gap-verification-evidence-contract",
}

P1_GAPS = {
    "gap-feedback-promotion",
    "gap-provider-redundancy",
    "gap-release-slo-loop",
}

P2_CRITICAL = {"VOL-007", "VOL-097", "VOL-104"}
P2_FUNCTIONAL_TASKS = {
    "P2-T1-DATA-01",
    "P2-T1-SEC-01",
    "P2-T1-INFER-01",
    "P2-T1-RECOVERY-01",
    "P2-T1-FUNCTIONAL-01",
}


class PhaseInheritanceError(RuntimeError):
    pass


def _load(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PhaseInheritanceError(f"cannot read {relative}") from exc
    if not isinstance(value, dict):
        raise PhaseInheritanceError(f"{relative} must contain an object")
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def verify(root: Path = ROOT, *, head_sha: str | None = None) -> dict[str, Any]:
    construction = _load(root, "machine/ai_app_construction.json")
    closure = _load(root, "machine/ai_closure_evidence.json")
    handoff = _load(root, "machine/ai_implementation_handoff.json")
    p1 = _load(root, "machine/ai_p1_terminal_closure.json")
    p2 = _load(root, "machine/ai_p2_functional_ai_closure.json")
    p2_map = _load(root, "machine/ai_p2_execution_map.json")
    p2_backlog = _load(root, "machine/ai_p2_task_backlog.json")
    build_queue = _load(root, "machine/ai_build_queue.json")

    errors: list[str] = []

    gaps = {
        str(item.get("id")): item
        for item in construction.get("gap_register", [])
        if isinstance(item, dict) and item.get("id")
    }
    if not (P0_GAPS | P1_GAPS) <= set(gaps):
        errors.append("canonical P0/P1 construction gap inventory is incomplete")
    for gap_id in sorted(P0_GAPS | P1_GAPS):
        if gaps.get(gap_id, {}).get("status") != "closed":
            errors.append(f"{gap_id} is not closed")

    closure_rows = {
        str(item.get("gap")): item
        for item in closure.get("entries", [])
        if isinstance(item, dict) and item.get("gap")
    }
    handoff_rows = {
        str(item.get("gap")): item
        for item in handoff.get("entries", [])
        if isinstance(item, dict) and item.get("gap")
    }
    for gap_id in sorted(P0_GAPS):
        row = closure_rows.get(gap_id)
        if not isinstance(row, dict):
            errors.append(f"{gap_id} has no P0 closure-evidence record")
            continue
        if row.get("gap_status") != "closed":
            errors.append(f"{gap_id} closure-evidence state is not closed")
        if row.get("implementation_state") != "complete":
            errors.append(f"{gap_id} implementation state is not complete")
        if row.get("closure_decision") != "closed":
            errors.append(f"{gap_id} closure decision is not closed")
        if row.get("blockers"):
            errors.append(f"{gap_id} still has closure blockers")
        if row.get("outstanding_evidence"):
            errors.append(f"{gap_id} still has outstanding closure evidence")

        handoff_row = handoff_rows.get(gap_id)
        if not isinstance(handoff_row, dict):
            errors.append(f"{gap_id} has no P0 implementation handoff")
        elif handoff_row.get("implementation_status") != "closed":
            errors.append(f"{gap_id} implementation handoff is not closed")

    if p1.get("status") != "closed":
        errors.append("P1 terminal closure is not closed")
    if p1.get("claim_scope") != "bounded_trustworthy_production_frontier":
        errors.append("P1 terminal claim scope drift")
    frontier = p1.get("frontier", {})
    if frontier.get("masterplan_volume_count") != 421:
        errors.append("P1 masterplan volume count must remain 421")
    if frontier.get("primary_p1_frontier_volume_count") != 107:
        errors.append("P1 primary frontier must remain 107 volumes")
    if frontier.get("deferred_to_p2_volume_count") != 314:
        errors.append("P1 deferred P2 frontier must remain 314 volumes")
    risk = p1.get("risk_evidence", {})
    if risk.get("required_blocking_count") != 0:
        errors.append("P1 terminal risk evidence has blocking obligations")
    if risk.get("required_unclassified_count") != 0:
        errors.append("P1 terminal risk evidence has unclassified obligations")
    if risk.get("accepted_risk_allowed") is not False:
        errors.append("P1 terminal closure must not silently allow accepted risk")

    if p2.get("status") != "closed":
        errors.append("P2 functional AI closure is not closed")
    if p2.get("claim_scope") != "provider_independent_functional_ai_frontier":
        errors.append("P2 functional AI claim scope drift")
    source = p2.get("source_scope", {})
    if source.get("p2_volume_count") != 314:
        errors.append("P2 source scope must inherit exactly 314 P1-deferred volumes")
    if source.get("scheduled_volume_count") != 57:
        errors.append("P2 scheduled volume count must remain 57")
    if source.get("queued_volume_count") != 257:
        errors.append("P2 queued volume count must remain 257")
    if set(map(str, p2.get("critical_volume_refs", []))) != P2_CRITICAL:
        errors.append("P2 critical functional volume set drift")

    requirements = p2.get("requirements", {})
    for name in (
        "local_model_identity_required",
        "governed_tool_authority_required",
        "durable_terminal_state_required",
        "reconnect_replay_required",
        "independent_verification_required",
        "exact_head_ci_required",
    ):
        if requirements.get(name) is not True:
            errors.append(f"P2 requirement {name} must remain true")
    for name in (
        "hosted_provider_credentials_required",
        "network_required_for_model_inference",
    ):
        if requirements.get(name) is not False:
            errors.append(f"P2 requirement {name} must remain false")

    p2_source = set(map(str, p2_map.get("source_scope", {}).get("volume_refs", [])))
    scheduled = set(map(str, p2_map.get("first_tranche", {}).get("scheduled_volume_refs", [])))
    queued = set(map(str, p2_map.get("first_tranche", {}).get("queued_volume_refs", [])))
    if len(p2_source) != 314 or len(scheduled) != 57 or len(queued) != 257:
        errors.append("P2 execution-map source partition count drift")
    if scheduled & queued or scheduled | queued != p2_source:
        errors.append("P2 execution-map scheduled/queued partition is invalid")

    tasks = {
        str(item.get("task_id")): item
        for item in p2_backlog.get("tasks", [])
        if isinstance(item, dict) and item.get("task_id")
    }
    missing_tasks = sorted(P2_FUNCTIONAL_TASKS - set(tasks))
    if missing_tasks:
        errors.append("P2 functional task inventory missing: " + ", ".join(missing_tasks))
    for task_id in sorted(P2_FUNCTIONAL_TASKS):
        task = tasks.get(task_id, {})
        if task.get("status") != "landed_unpromoted":
            errors.append(f"{task_id} must remain landed_unpromoted until signoff")
        if task.get("completion_checkbox") is not False:
            errors.append(f"{task_id} must not self-promote completion")
        if task.get("implementation_signed") is not False:
            errors.append(f"{task_id} must not self-sign implementation")
        if task.get("verification_signed") is not False:
            errors.append(f"{task_id} must not self-sign verification")

    queue_tasks = build_queue.get("tasks", [])
    queue_states: dict[str, int] = {}
    for task in queue_tasks:
        if not isinstance(task, dict):
            continue
        state = str(task.get("status", "unknown"))
        queue_states[state] = queue_states.get(state, 0) + 1

    resolved_head = (
        (head_sha or "").strip()
        or os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or "unknown"
    )

    return {
        "schema_version": "skeleton.ai.phase_inheritance_receipt.v1",
        "verifier": "ai-phase-inheritance-v1",
        "head_sha": resolved_head,
        "valid": not errors,
        "errors": errors,
        "phase_state": {
            "p0_construction_gaps_closed": sum(
                1 for gap_id in P0_GAPS if gaps.get(gap_id, {}).get("status") == "closed"
            ),
            "p0_construction_gap_total": len(P0_GAPS),
            "p1_terminal_status": p1.get("status"),
            "p1_primary_volume_count": frontier.get("primary_p1_frontier_volume_count"),
            "p2_functional_status": p2.get("status"),
            "p2_scheduled_volume_count": source.get("scheduled_volume_count"),
            "p2_queued_volume_count": source.get("queued_volume_count"),
        },
        "atomic_accountability_queue": {
            "role": "construction/signoff ledger; not terminal phase-closure authority",
            "task_count": len(queue_tasks),
            "status_counts": queue_states,
        },
        "digests": {
            "construction": _digest(construction),
            "p0_closure": _digest(closure),
            "p0_handoff": _digest(handoff),
            "p1_terminal": _digest(p1),
            "p2_functional": _digest(p2),
            "p2_execution_map": _digest(p2_map),
            "p2_backlog": _digest(p2_backlog),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head-sha")
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify(ROOT, head_sha=args.head_sha)
    except PhaseInheritanceError as exc:
        print(f"AI phase inheritance: rejected: {exc}", file=sys.stderr)
        return 2

    if args.evidence_out is not None:
        args.evidence_out.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    if not receipt["valid"]:
        if not args.json:
            for error in receipt["errors"]:
                print(f"  - {error}", file=sys.stderr)
        return 1
    if not args.json:
        print(
            "AI phase inheritance: OK "
            f"(head={receipt['head_sha']}, "
            f"P0={receipt['phase_state']['p0_construction_gaps_closed']}/"
            f"{receipt['phase_state']['p0_construction_gap_total']}, "
            f"P1={receipt['phase_state']['p1_terminal_status']}, "
            f"P2={receipt['phase_state']['p2_functional_status']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
