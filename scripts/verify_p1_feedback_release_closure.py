#!/usr/bin/env python3
"""Independent verifier for P1 feedback-promotion and release-SLO surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

SURFACES: dict[str, tuple[str, ...]] = {
    "skeleton/learning/promotion.py": (
        "class ExperimentSpec",
        "class FeedbackLedger",
        "class EvaluationReceipt",
        "class FeedbackPromotionPipeline",
        "holdout feedback cannot enter promotion evaluation",
        "feedback cannot be retained without explicit consent",
        "def rollback(",
    ),
    "skeleton/release/slo_promotion.py": (
        "class ReleaseSLOPolicy",
        "class CanarySLOSignal",
        "class OperatorOverride",
        "class ReleaseDecisionReceipt",
        "class ReleaseSLOPromotionController",
        "operator override cannot promote failed SLO evidence",
        "release SLO signals must come from observability",
    ),
    "skeleton/testing/test_feedback_promotion.py": (
        "test_assignment_is_deterministic_and_experiment_isolated",
        "test_feedback_collection_requires_consent_and_declared_data_use",
        "test_holdout_feedback_isolated_from_promotion_evaluation",
        "test_rollback_restores_baseline_with_promotion_lineage",
    ),
    "skeleton/testing/test_release_slo_promotion.py": (
        "test_healthy_observability_promotes_with_order_stable_receipt",
        "test_unhealthy_canary_automatically_rolls_back",
        "test_operator_cannot_promote_over_failed_slo_evidence",
    ),
    ".github/workflows/p1-feedback-release-closure.yml": (
        "Feedback and release contracts",
        "Independent P1 verifier",
        "test_feedback_promotion.py",
        "test_release_slo_promotion.py",
    ),
}

EXPECTED_GAPS = {
    "gap-feedback-promotion": "feedback-learning",
    "gap-release-slo-loop": "deployment-release",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(_read(path))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    digests: dict[str, str] = {}

    for rel, tokens in SURFACES.items():
        path = root / rel
        if not path.is_file():
            errors.append(f"P1 closure surface is missing: {rel}")
            continue
        source = _read(path)
        for token in tokens:
            if token not in source:
                errors.append(f"{rel} lost required token: {token}")
        digests[rel] = hashlib.sha256(source.encode("utf-8")).hexdigest()

    construction_path = root / "machine/ai_app_construction.json"
    gap_state: dict[str, str] = {}
    if not construction_path.is_file():
        errors.append("machine/ai_app_construction.json is missing")
    else:
        construction = _load(construction_path)
        rows = construction.get("gap_register")
        if not isinstance(rows, list):
            errors.append("gap_register must be a list")
        else:
            by_id = {
                str(row.get("id")): row
                for row in rows
                if isinstance(row, dict) and row.get("id")
            }
            for gap_id, plane in EXPECTED_GAPS.items():
                row = by_id.get(gap_id)
                if row is None:
                    errors.append(f"P1 masterplan gap is missing: {gap_id}")
                    continue
                if row.get("plane") != plane:
                    errors.append(f"P1 masterplan plane drift: {gap_id}")
                status = str(row.get("status") or "")
                gap_state[gap_id] = status
                if status != "closed":
                    errors.append(
                        f"P1 masterplan gap must remain closed: {gap_id}"
                    )

    return {
        "schema_version": 1,
        "verifier": "independent-p1-feedback-release-v1",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "valid": not errors,
        "errors": errors,
        "surface_digests": digests,
        "gap_state": gap_state,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-out")
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args()
    receipt = verify_repository()
    if args.evidence_out:
        Path(args.evidence_out).write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.print_evidence:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
