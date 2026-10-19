"""Read-only Dragon witness follow-up queue for the canonical Jeeves studio.

The queue prioritizes unqualified gates and missing independent observations.
It never makes a quality gate pass, records a new event or promotes learning.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import jeeves_dragon_observer as observer

MAX_QUEUE_PAGE = 128


def review_queue(root: Path, *, page: int = 0, page_size: int = 32) -> dict[str, Any]:
    """Reconcile a deterministic work queue with the trusted producer ledger."""
    if (type(page) is not int or page < 0 or page > 1_000_000
            or type(page_size) is not int or not 1 <= page_size <= MAX_QUEUE_PAGE):
        raise observer.WitnessError("review queue requires bounded pagination")

    report = observer.coverage(root)  # checks consent, source and witness chain
    rows = []
    for item in report["records"]:
        missed = item["canonical_checks"] - item["dragon_observed_checks"]
        if missed < 0:
            raise observer.WitnessError("witness count exceeds canonical source")
        if item["qualified"] and missed == 0:
            continue
        # Do not replace authoritative quality gate outcomes with telemetry.
        if not item["automated_checker_registered"]:
            priority, reason = 0, "independent_evaluator_missing"
        elif item["latest_outcome"] == "failed":
            priority, reason = 1, "canonical_failure_needs_investigation"
        elif item["latest_outcome"] in ("blocked", "cancelled"):
            priority, reason = 2, "prerequisite_or_execution_blocked"
        elif item["latest_outcome"] == "not_evaluated":
            priority, reason = 3, "canonical_check_not_attempted"
        elif missed:
            priority, reason = 4, "unreconciled_canonical_observation"
        else:
            priority, reason = 5, "canonical_requalification_required"
        rows.append({
            "gate": item["gate"],
            "phase": item["phase"],
            "priority": priority,
            "reason": reason,
            "canonical_checks": item["canonical_checks"],
            "missed_witness_receipts": missed,
            "latest_canonical_outcome": item["latest_outcome"],
            "expected_evidence_owner": item["expected_evidence_owner"],
            "next_action": (
                "reconcile existing canonical receipts before follow-up" if missed
                else item["next_action"]
            ),
            "gate_completed_by_this_queue": False,
            "training_promotion_eligible": False,
        })
    rows.sort(key=lambda row: (row["priority"], -row["missed_witness_receipts"], row["gate"]))
    start = page * page_size
    subset = rows[start:start + page_size]
    return {
        "schema": "skeleton.jeeves.dragon_review_queue.v1",
        "action": "dragon-observe-review-queue",
        "total": len(rows), "page": page, "page_size": page_size,
        "next_page": page + 1 if start + len(subset) < len(rows) else None,
        "items": subset,
        "source_gate_count": report["required_gates"],
        "qualified_gates_from_canonical_evidence": report["qualified_gates"],
        "unwitnessed_canonical_checks": report["unwitnessed_canonical_checks"],
        "actual_screen_capture": False, "independent_game_completion": False,
        "model_weights_updated": False, "automatic_gate_promotion": False,
    }
