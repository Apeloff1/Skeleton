#!/usr/bin/env python3
"""Build exact-head evidence candidates for P1 risk classification batch 4.

The verifier is non-authoritative. It classifies a bounded set of previously
unclassified P1 risk obligations as high severity only when repository-owned
contracts and regressions directly mitigate the stated risk. It emits evidence
candidates but never writes EVID-04 bindings, accepts risk, signs accountability,
or changes maturity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconcile_p1_risk_evidence import (  # noqa: E402
    ADVERSARIAL,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
    ROOT,
    RiskKind,
    derive_obligations,
)


_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
CATEGORY = "risk_classification_evidence"
BATCH_ID = "p1-risk-classification-batch4"
PROPOSED_SEVERITY = "high"


class RiskClassificationEvidenceError(RuntimeError):
    """Risk classification evidence is malformed or incomplete."""


COVERAGE: dict[tuple[str, str], dict[str, Any]] = {
    ("VOL-056", "orphan gaps"): {
        "sources": [
            "scripts/reconcile_p1_risk_evidence.py",
            "skeleton/contracts/risk_evidence.py",
        ],
        "tests": ["tests/test_p1_risk_evidence_reconciliation.py"],
        "markers": {
            "scripts/reconcile_p1_risk_evidence.py": [
                "derive_obligations(",
                '"volume_gap_count"',
                "risk obligation inventory drift",
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                "test_inventory_drift_fails_closed",
                "test_unknown_binding_identity_fails_closed",
            ],
        },
    },
    ("VOL-056", "status inflation"): {
        "sources": [
            "scripts/reconcile_p1_risk_evidence.py",
            ".github/workflows/p1-risk-evidence-binding.yml",
        ],
        "tests": ["tests/test_p1_risk_evidence_reconciliation.py"],
        "markers": {
            "scripts/reconcile_p1_risk_evidence.py": [
                '"unresolved_blocking_count"',
                "--require-resolved",
                "unresolved blocking obligations",
            ],
            ".github/workflows/p1-risk-evidence-binding.yml": [
                "--require-resolved",
                "terminal-required",
            ],
        },
    },
    ("VOL-056", "duplicate/conflicting records"): {
        "sources": [
            "scripts/reconcile_p1_risk_evidence.py",
            "skeleton/contracts/risk_evidence.py",
        ],
        "tests": [
            "tests/test_p1_risk_evidence_reconciliation.py",
            "skeleton/testing/test_risk_evidence.py",
        ],
        "markers": {
            "scripts/reconcile_p1_risk_evidence.py": [
                "duplicate risk binding",
                "bindings reference unknown obligations",
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                "test_duplicate_binding_fails_closed",
                "test_unknown_binding_identity_fails_closed",
            ],
        },
    },
    ("VOL-057", "critical risk hidden by aggregate status"): {
        "sources": [
            "scripts/reconcile_p1_risk_evidence.py",
            "skeleton/contracts/risk_evidence.py",
        ],
        "tests": ["tests/test_p1_risk_evidence_reconciliation.py"],
        "markers": {
            "scripts/reconcile_p1_risk_evidence.py": [
                '"records": rows',
                '"severity": default_severity.value',
                '"blocking": default_blocking',
            ],
            "tests/test_p1_risk_evidence_reconciliation.py": [
                "test_one_real_binding_changes_only_its_own_resolution",
                "test_live_p1_risk_inventory_is_deterministic_and_non_authoritative",
            ],
        },
    },
    ("VOL-057", "paper control without evidence"): {
        "sources": ["skeleton/contracts/risk_evidence.py"],
        "tests": ["skeleton/testing/test_risk_evidence.py"],
        "markers": {
            "skeleton/contracts/risk_evidence.py": [
                "evidence disposition requires evidence",
                "risk evidence source must be materialized, not planned",
            ],
            "skeleton/testing/test_risk_evidence.py": [
                "test_materialized_evidence_resolves_high_risk",
                "test_planned_evidence_source_is_rejected",
            ],
        },
    },
    ("VOL-059", "false green aggregation"): {
        "sources": [
            "machine/p1_required_gate_authority.json",
            "skeleton/contracts/promotion_gates.py",
        ],
        "tests": [
            "skeleton/testing/test_promotion_gates.py",
            "tests/test_p1_required_gate_authority.py",
        ],
        "markers": {
            "machine/p1_required_gate_authority.json": [
                '"all_required_gates_must_pass": true',
                '"skipped_conclusion": "reject"',
                '"cancelled_conclusion": "reject"',
            ],
            "skeleton/testing/test_promotion_gates.py": [
                "test_missing_required_gate_fails_closed",
                "test_non_success_or_nonterminal_gate_fails_closed",
                "test_duplicate_exact_head_observation_fails_closed",
            ],
        },
    },
    ("VOL-059", "non-reproducible failure"): {
        "sources": [
            "skeleton/contracts/reproducibility.py",
            "machine/p1_reproducibility_policy.json",
        ],
        "tests": [
            "skeleton/testing/test_reproducibility.py",
            "tests/test_p1_reproducibility_bundle.py",
        ],
        "markers": {
            "skeleton/contracts/reproducibility.py": [
                "failure_digest: str | None = None",
                "def evaluate_replay(",
                "ReplayDisposition",
            ],
            "skeleton/testing/test_reproducibility.py": [
                "test_failed_replay_is_not_misreported_as_incompatibility",
                "test_failed_replay_with_infrastructure_drift_is_incompatible",
            ],
        },
    },
    ("VOL-078", "hidden dependency"): {
        "sources": [
            "skeleton/contracts/reproducibility.py",
            "machine/p1_reproducibility_policy.json",
        ],
        "tests": [
            "skeleton/testing/test_reproducibility.py",
            "tests/test_p1_reproducibility_bundle.py",
        ],
        "markers": {
            "skeleton/contracts/reproducibility.py": [
                "configuration_digest: str",
                "environment_digest: str",
                "runner_digest: str",
                "budget_digest: str",
                "inputs: tuple[EvidenceRef, ...]",
            ],
            "skeleton/testing/test_reproducibility.py": [
                "test_replay_infrastructure_drift_is_deterministically_incompatible",
                "test_bundle_input_order_and_duplicates_are_canonicalized",
            ],
        },
    },
    ("VOL-078", "false deterministic claim"): {
        "sources": ["skeleton/contracts/reproducibility.py"],
        "tests": [
            "skeleton/testing/test_reproducibility.py",
            "tests/test_p1_reproducibility_bundle.py",
        ],
        "markers": {
            "skeleton/contracts/reproducibility.py": [
                "def evaluate_replay(",
                "expected_evidence_digest",
                "ReplayDisposition.REPRODUCED",
            ],
            "skeleton/testing/test_reproducibility.py": [
                "test_evidence_drift_is_incompatible_even_when_subject_matches",
                "test_receipt_identity_drift_is_incompatible",
            ],
        },
    },
    ("VOL-420", "breadth inflation"): {
        "sources": [
            "scripts/check_ai_scope_freeze.py",
            "machine/ai_scope_freeze_adrs.json",
        ],
        "tests": ["skeleton/testing/test_architecture_scope_freeze.py"],
        "markers": {
            "scripts/check_ai_scope_freeze.py": [
                "active P1 scope requires exactly",
                "active P1 scope-freeze register must contain zero applied ADRs",
            ],
            "skeleton/testing/test_architecture_scope_freeze.py": [
                "test_direct_top_level_volume_insertion_fails_closed",
                "test_breadth_freeze_application_policy_cannot_be_weakened",
            ],
        },
    },
    ("VOL-420", "misfit requirement forced into wrong volume"): {
        "sources": [
            "scripts/check_ai_scope_freeze.py",
            "machine/ai_scope_freeze_adrs.json",
        ],
        "tests": ["skeleton/testing/test_architecture_scope_freeze.py"],
        "markers": {
            "scripts/check_ai_scope_freeze.py": [
                "approved ADR requires decision_summary",
                "applied scope expansion is forbidden during active P1",
            ],
            "skeleton/testing/test_architecture_scope_freeze.py": [
                "test_adr_must_analyze_existing_canonical_volumes",
                "test_approved_future_adr_requires_identity_bound_approvals",
            ],
        },
    },
    ("VOL-077", "production contamination"): {
        "sources": ["skeleton/eval/experiment_registry.py"],
        "tests": ["skeleton/testing/test_experiment_registry.py"],
        "markers": {
            "skeleton/eval/experiment_registry.py": [
                "external_side_effects_allowed: bool = False",
                '"production_authority": False',
            ],
            "skeleton/testing/test_experiment_registry.py": [
                "test_shadow_traffic_is_bounded_and_side_effect_free",
                "test_manifest_is_deterministic_and_non_authoritative",
            ],
        },
    },
    ("VOL-082", "benchmark leakage"): {
        "sources": ["skeleton/eval/benchmark_registry.py"],
        "tests": ["skeleton/testing/test_benchmark_registry.py"],
        "markers": {
            "skeleton/eval/benchmark_registry.py": [
                "class ContaminationStatus(str, Enum):",
                "contamination_evidence: tuple[EvidenceRef, ...]",
                "contamination-not-clean",
            ],
            "skeleton/testing/test_benchmark_registry.py": [
                "test_non_clean_contamination_blocks",
                "test_duplicate_split_content_is_rejected",
            ],
        },
    },
    ("VOL-082", "cherry-picked baselines"): {
        "sources": ["skeleton/eval/benchmark_registry.py"],
        "tests": ["skeleton/testing/test_benchmark_registry.py"],
        "markers": {
            "skeleton/eval/benchmark_registry.py": [
                "baseline_observation_digest",
                "baseline-sample-count-too-low",
                "baseline-evaluator-id-mismatch",
            ],
            "skeleton/testing/test_benchmark_registry.py": [
                "test_improvement_claim_rejects_non_improvement",
                "test_improvement_claim_rejects_under_sampling_and_evaluator_drift",
            ],
        },
    },
    ("VOL-414", "candidate side effect leaks"): {
        "sources": ["skeleton/eval/shadow_traffic.py"],
        "tests": ["skeleton/testing/test_shadow_traffic.py"],
        "markers": {
            "skeleton/eval/shadow_traffic.py": [
                "external_side_effect_count: int = 0",
                "persistent_write_count: int = 0",
                "shadow-canonical-write-detected",
            ],
            "skeleton/testing/test_shadow_traffic.py": [
                "test_shadow_side_effect_profiles_fail_closed",
                "test_canonical_write_count_is_structurally_forbidden",
                "test_policy_cannot_enable_shadow_side_effects",
            ],
        },
    },
    ("VOL-414", "non-comparable traffic"): {
        "sources": ["skeleton/eval/shadow_traffic.py"],
        "tests": ["skeleton/testing/test_shadow_traffic.py"],
        "markers": {
            "skeleton/eval/shadow_traffic.py": [
                "champion_latency_ms: float",
                "challenger_latency_ms: float",
                "comparator_digest: str",
                "independent: bool = True",
            ],
            "skeleton/testing/test_shadow_traffic.py": [
                "test_fraction_data_class_and_tenant_eligibility_fail_closed",
                "test_evaluator_must_be_independent_and_not_shadow_agent",
                "test_source_and_input_substitution_block",
            ],
        },
    },
    ("VOL-415", "benchmark gaming"): {
        "sources": [
            "skeleton/eval/champion_registry.py",
            "skeleton/eval/benchmark_registry.py",
        ],
        "tests": [
            "skeleton/testing/test_champion_registry.py",
            "skeleton/testing/test_benchmark_registry.py",
        ],
        "markers": {
            "skeleton/eval/champion_registry.py": [
                "baseline-is-not-current-champion",
                "benchmark_manifest_digest",
                "improvement_claim",
            ],
            "skeleton/testing/test_champion_registry.py": [
                "test_baseline_must_be_current_champion",
                "test_candidate_cannot_qualify_from_rejected_benchmark",
                "test_non_improvement_cannot_advance_champion",
            ],
        },
    },
    ("VOL-415", "candidate overwrites champion"): {
        "sources": ["skeleton/eval/champion_registry.py"],
        "tests": ["skeleton/testing/test_champion_registry.py"],
        "markers": {
            "skeleton/eval/champion_registry.py": [
                "Every champion transition is append-only",
                "promotion decision champion is stale",
                "def apply_promotion(",
            ],
            "skeleton/testing/test_champion_registry.py": [
                "test_accepted_comparative_promotion_is_append_only",
                "test_stale_promotion_decision_cannot_apply_to_changed_registry",
                "test_transition_chain_tampering_is_rejected",
            ],
        },
    },
    ("VOL-419", "same failure repeated"): {
        "sources": [
            "skeleton/eval/failure_knowledge.py",
            "skeleton/eval/regression_corpus.py",
        ],
        "tests": ["skeleton/testing/test_failure_knowledge.py"],
        "markers": {
            "skeleton/eval/failure_knowledge.py": [
                "failure_fingerprint: str",
                "target_regression_case_digest",
                "source_digest: str",
            ],
            "skeleton/testing/test_failure_knowledge.py": [
                "test_repeated_fingerprint_cannot_split_across_regression_targets",
                "test_repeated_fingerprint_cannot_have_conflicting_disposition",
            ],
        },
    },
    ("VOL-419", "anecdote becomes dogma"): {
        "sources": ["skeleton/eval/failure_knowledge.py"],
        "tests": ["skeleton/testing/test_failure_knowledge.py"],
        "markers": {
            "skeleton/eval/failure_knowledge.py": [
                "source_kind: FailureSourceKind",
                "source_digest: str",
                "non-applicability review must be independent",
                '"production_authority": False',
            ],
            "skeleton/testing/test_failure_knowledge.py": [
                "test_non_applicable_requires_independent_exact_decision",
                "test_regression_case_digest_substitution_blocks",
                "test_learning_signal_has_no_production_or_self_modify_authority",
            ],
        },
    },
}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RiskClassificationEvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise RiskClassificationEvidenceError(f"{path} must contain an object")
    return value


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_paths(root: Path, spec: dict[str, Any]) -> tuple[list[Path], list[Path]]:
    sources = [root / item for item in spec["sources"]]
    tests = [root / item for item in spec["tests"]]
    for path in [*sources, *tests]:
        if not path.is_file():
            raise RiskClassificationEvidenceError(
                f"evidence path is missing: {path.relative_to(root)}"
            )
    return sources, tests


def _validate_markers(root: Path, spec: dict[str, Any], identity: tuple[str, str]) -> None:
    declared = set(spec["sources"]) | set(spec["tests"])
    markers = spec.get("markers")
    if not isinstance(markers, dict) or not markers:
        raise RiskClassificationEvidenceError(f"{identity}: marker map is empty")
    for relative, required in markers.items():
        if relative not in declared:
            raise RiskClassificationEvidenceError(
                f"{identity}: undeclared marker path {relative}"
            )
        text = (root / relative).read_text(encoding="utf-8")
        missing = [item for item in required if item not in text]
        if missing:
            raise RiskClassificationEvidenceError(
                f"{identity}: {relative} missing contract markers: "
                + ",".join(missing)
            )


def build_risk_classification_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise RiskClassificationEvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    canonical = {
        "master_plan": root / MASTER,
        "p1_execution_map": root / P1_MAP,
        "adversarial_closure": root / ADVERSARIAL,
        "risk_policy": root / POLICY,
        "risk_registry": root / REGISTRY,
    }
    before = {name: _digest_file(path) for name, path in canonical.items()}

    master = _load(canonical["master_plan"])
    p1_map = _load(canonical["p1_execution_map"])
    adversarial = _load(canonical["adversarial_closure"])
    policy = _load(canonical["risk_policy"])
    registry = _load(canonical["risk_registry"])
    obligations = derive_obligations(master, p1_map, adversarial, policy)

    risk_by_identity = {
        (item.source_ref.split(":", 1)[0], item.statement): item
        for item in obligations
        if item.kind is RiskKind.RISK
    }
    registry_rows = registry.get("records")
    if not isinstance(registry_rows, list):
        raise RiskClassificationEvidenceError("risk registry records must be a list")
    bound_ids: set[str] = set()
    for index, row in enumerate(registry_rows):
        if not isinstance(row, dict):
            raise RiskClassificationEvidenceError(
                f"risk registry record {index} must be an object"
            )
        obligation_id = row.get("obligation_id")
        if not isinstance(obligation_id, str) or not obligation_id:
            raise RiskClassificationEvidenceError(
                f"risk registry record {index} has invalid obligation_id"
            )
        if obligation_id in bound_ids:
            raise RiskClassificationEvidenceError(
                f"duplicate governed binding identity: {obligation_id}"
            )
        bound_ids.add(obligation_id)

    known_ids = {item.obligation_id for item in obligations}
    unknown = sorted(bound_ids - known_ids)
    if unknown:
        raise RiskClassificationEvidenceError(
            "risk registry references unknown obligations: " + ",".join(unknown)
        )

    records: list[dict[str, Any]] = []
    for identity in sorted(COVERAGE):
        obligation = risk_by_identity.get(identity)
        if obligation is None:
            raise RiskClassificationEvidenceError(
                f"missing canonical risk obligation: {identity[0]}: {identity[1]}"
            )
        if obligation.default_severity.value != "unclassified":
            raise RiskClassificationEvidenceError(
                f"{identity}: risk is no longer unclassified by default"
            )
        spec = COVERAGE[identity]
        source_paths, test_paths = _validate_paths(root, spec)
        _validate_markers(root, spec, identity)

        packet: dict[str, Any] = {
            "batch_id": BATCH_ID,
            "volume_key": identity[0],
            "statement": identity[1],
            "obligation_id": obligation.obligation_id,
            "obligation_digest": obligation.obligation_digest,
            "source_ref": obligation.source_ref,
            "expected_head": expected_head,
            "proposed_severity": PROPOSED_SEVERITY,
            "proposed_disposition": "evidence",
            "source_digests": {
                str(path.relative_to(root)): _digest_file(path)
                for path in source_paths
            },
            "test_digests": {
                str(path.relative_to(root)): _digest_file(path)
                for path in test_paths
            },
            "verified_contract_markers": {
                path: list(markers)
                for path, markers in sorted(spec["markers"].items())
            },
            "binding_present": obligation.obligation_id in bound_ids,
            "non_authoritative": True,
            "creates_binding": False,
            "accepts_risk": False,
            "signs_accountability": False,
            "promotes_maturity": False,
        }
        packet["packet_digest"] = _canonical_digest(packet)
        packet["candidate_evidence_ref"] = {
            "source": (
                f"p1:risk-classification-batch4:"
                f"{obligation.obligation_id}:{expected_head}"
            ),
            "digest": packet["packet_digest"],
            "category": CATEGORY,
        }
        records.append(packet)

    if len(records) != 20:
        raise RiskClassificationEvidenceError(
            f"expected 20 covered risks, got {len(records)}"
        )
    if len({row["obligation_id"] for row in records}) != 20:
        raise RiskClassificationEvidenceError("duplicate covered risk obligation")

    after = {name: _digest_file(path) for name, path in canonical.items()}
    if before != after:
        raise RiskClassificationEvidenceError(
            "canonical sources changed during risk evidence build"
        )

    report: dict[str, Any] = {
        "schema_version": 1,
        "engine": "p1-risk-classification-evidence-batch4-v1",
        "batch_id": BATCH_ID,
        "expected_head": expected_head,
        "category": CATEGORY,
        "covered_risk_count": len(records),
        "covered_volume_count": len({row["volume_key"] for row in records}),
        "proposed_severity": PROPOSED_SEVERITY,
        "already_bound_count": sum(1 for row in records if row["binding_present"]),
        "candidate_binding_count": sum(1 for row in records if not row["binding_present"]),
        "non_authoritative": True,
        "creates_bindings": False,
        "accepts_risk": False,
        "signs_accountability": False,
        "promotes_maturity": False,
        "canonical_source_digests": before,
        "records": records,
    }
    report["report_digest"] = _canonical_digest(report)
    return report


def _canonical_text(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument("--print-candidates", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_risk_classification_evidence(
            ROOT,
            expected_head=args.expected_head,
        )
    except RiskClassificationEvidenceError as exc:
        print(f"P1 risk classification evidence: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_canonical_text(report), encoding="utf-8")

    if args.print_summary:
        print(json.dumps({
            key: report[key]
            for key in (
                "engine",
                "batch_id",
                "expected_head",
                "covered_risk_count",
                "covered_volume_count",
                "proposed_severity",
                "already_bound_count",
                "candidate_binding_count",
                "report_digest",
            )
        }, indent=2, sort_keys=True))

    if args.print_candidates:
        print(json.dumps([
            {
                "volume_key": row["volume_key"],
                "statement": row["statement"],
                "obligation_id": row["obligation_id"],
                "obligation_digest": row["obligation_digest"],
                "proposed_severity": row["proposed_severity"],
                "candidate_evidence_ref": row["candidate_evidence_ref"],
            }
            for row in report["records"]
        ], indent=2, sort_keys=True))

    print(
        "P1 risk classification evidence: OK "
        f"({report['covered_risk_count']} risks across "
        f"{report['covered_volume_count']} volumes; "
        f"{report['candidate_binding_count']} candidates)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
