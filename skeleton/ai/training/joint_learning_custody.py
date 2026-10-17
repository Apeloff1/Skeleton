"""Read-only joint SDK + ROM training custody checkpoint for Jeeves/Dragon.

Both source families are rechecked by their existing canonical owners. This
planner cannot grant rights, load a ROM, execute an SDK, train the speaking
model, promote neural weights or certify console hardware compatibility.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .rom_fleet_audit import audit_fleet_all
from .sdk_custody_drift import _digest, compare_custody

SCHEMA = "skeleton.jeeves.joint_training_custody.v1"


def audit_joint_learning_custody(
    sdk_before: dict[str, Any],
    sdk_after: dict[str, Any],
    *,
    rom_root: Path,
    frozen_inventory: Path,
    rom_approvals: Path,
    rom_receipts: Path,
    page_limit: int = 64,
    max_pages: int = 0,
) -> dict[str, Any]:
    """Reaudit current rights and report distinct cross-source blockers.

    A valid SHA report is not a license or an authentic independent gameplay
    witness. Even zero reported blockers CANNOT authorize automatic model
    promotion. Page-capped reports remain visibly incomplete.
    """
    drift = compare_custody(sdk_before, sdk_after)
    fleet = audit_fleet_all(
        rom_root, frozen_inventory, rom_approvals, rom_receipts,
        limit=page_limit, max_pages=max_pages,
    )
    if fleet.get("production_jeeves_weights_modified") is not False:
        raise ValueError("fleet evidence is not a permitted training-custody input")
    counts = fleet["totals"]
    needs_rights = counts.get("rights_review_required", 0)
    drifted = drift["changed_documents"]
    missing = counts.get("approved_but_no_receipt", 0)
    invalid = counts.get("invalid_or_stale_receipt_sources", 0)
    source_changed = counts.get("source_identity_changed", 0)
    truncated = fleet["finished_inventory"] is not True
    open_reviews = drifted + needs_rights + missing + invalid + source_changed
    if truncated:
        state = "fleet_page_horizon_incomplete"
    elif drifted or needs_rights:
        state = "cross_source_license_review_required"
    elif invalid or source_changed:
        state = "emulator_source_or_evidence_reverification_required"
    elif missing:
        state = "approved_rom_training_evidence_missing"
    else:
        state = "read_only_custody_reconciled_requires_independent_execution"
    result = {
        "schema_version": SCHEMA,
        "status": state,
        "sdk": {
            "before_manifest_sha256": sdk_before["source_manifest_sha256"],
            "after_manifest_sha256": sdk_after["source_manifest_sha256"],
            "source_manifest_changed": drift["source_manifest_changed"],
            "drift_digest": drift["drift_digest"],
            "changed_documents": drifted,
            "unchanged_documents": drift["unchanged_documents"],
            "review_required": bool(drifted),
        },
        "rom": {
            "inventory_sha256": fleet["inventory_sha256"],
            "approval_manifest_sha256": fleet["approval_manifest_sha256"],
            "pages_audited": fleet["pages_audited"],
            "finished_inventory": fleet["finished_inventory"],
            "next_cursor": fleet["next_cursor"],
            "candidate_files": fleet["total_snapshot_candidate_files"],
            "approved_but_not_trained": missing,
            "rights_review_required": needs_rights,
            "stale_or_invalid_receipt_sources": invalid,
            "source_identity_changed": source_changed,
            "verified_q_policy_source_claims": counts.get("verified_q_policy_sources", 0),
            "shadow_neural_candidate_claims": counts.get(
                "verified_neural_candidate_sources", 0
            ),
            "source_execution_coverage_pct": fleet["source_execution_coverage_pct"],
            "report_is_read_only_secondary_accounting": True,
        },
        "open_review_conditions_in_audited_scope": open_reviews,
        "no_unbounded_rom_bytes_exported": True,
        "raw_sdk_corpus_or_rom_content_included": False,
        "hardware_compatibility_verified": False,
        "independent_dragon_or_adversarial_witness_complete": False,
        "actual_jeeves_speaking_model_weight_updates": 0,
        "automatic_weight_promotion_authorized": False,
        "operator_license_reapproval_still_required": bool(drifted or needs_rights),
        "model_release_or_game_completion_certified": False,
    }
    result["custody_digest"] = _digest(result)
    return result
