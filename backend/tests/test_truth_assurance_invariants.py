from copy import deepcopy

from core.system_assurance import evaluate_assurance


def _verification():
    return {
        "truth_gated": True,
        "speculation_authoritative": False,
        "model_consensus_is_empirical_evidence": False,
        "semantic_similarity_is_truth_identity": False,
        "evidence_registry": {
            "cross_process_locking": True,
            "lock_backend": "fcntl",
            "truth_eligible_default": True,
        },
        "source_lineage": {
            "cross_process_locking": True,
            "lock_backend": "fcntl",
            "sources": 0,
            "unresolved_lineage": 0,
        },
        "truth_ledger": {
            "cross_process_locking": True,
            "claims": 0,
            "authoritative": 0,
            "revoked": 0,
            "expired": 0,
        },
        "claim_dependencies": {
            "cross_process_locking": True,
            "lock_backend": "fcntl",
            "claims": 0,
            "edges": 0,
        },
        "calibration": {
            "version": 1,
            "cross_process_locking": True,
            "lock_backend": "fcntl",
            "truth_authority": False,
        },
        "knowledge": {"surface_count": 4},
        "verification_policy": {
            "require_empirical_support": True,
            "require_provenance_verified": True,
            "require_reproducibility_signal": True,
            "require_independent_replication_for_experiments": True,
            "require_falsifiable_claim": True,
            "contradiction_blocks": True,
        },
    }


def _operations(verification):
    return {
        "audit_sequence": 0,
        "audit_head": None,
        "audit_health": {"cross_process_locking": True, "verified": True, "lock_backend": "fcntl"},
        "outbox_capacity_remaining": 128,
        "outbox_health": {
            "cross_process_locking": True,
            "leased_intent_factory": True,
            "lock_backend": "fcntl",
            "sequence_meta_version": 1,
            "next_sequence": 1,
        },
        "curiosity": {"verification": verification},
    }


def _report(verification):
    return evaluate_assurance(
        lifecycle=[],
        operations=_operations(verification),
        executor_bindings=[{"effect_class": "query", "replay_safe": True}],
        executor_coverage={"coverage_pct": 71.4},
        receipt_stats={"version": 2},
        readiness={"ready_pct": 71.4, "policy_gaps": 0, "unsafe_actions": 0},
    )


def test_truth_assurance_accepts_safe_epistemic_contract():
    report = _report(_verification())
    assert report.hard_failures == 0
    failed = [row.id for row in report.invariants if row.severity == "hard" and not row.passed]
    assert failed == []


def test_unbound_evidence_default_blocks_deployment():
    verification = deepcopy(_verification())
    verification["evidence_registry"]["truth_eligible_default"] = False
    report = _report(verification)
    assert report.posture == "blocked"
    assert any(row.id == "truth.evidence-default-citation-bound" and not row.passed for row in report.invariants)


def test_calibration_cannot_become_truth_authority():
    verification = deepcopy(_verification())
    verification["calibration"]["truth_authority"] = True
    report = _report(verification)
    assert report.posture == "blocked"
    assert any(row.id == "truth.calibration-nonauthoritative" and not row.passed for row in report.invariants)


def test_semantic_similarity_cannot_become_truth_identity():
    verification = deepcopy(_verification())
    verification["semantic_similarity_is_truth_identity"] = True
    report = _report(verification)
    assert report.posture == "blocked"
    assert any(row.id == "truth.semantic-similarity-not-identity" and not row.passed for row in report.invariants)
