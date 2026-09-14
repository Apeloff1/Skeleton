from copy import deepcopy

from core.system_assurance import evaluate_assurance


def _deployment_status():
    return {
        "authorization": {
            "version": 1, "issued": 0, "consumed": 0, "outstanding": 0,
            "head_sha256": "", "cross_process_locking": True, "lock_backend": "fcntl", "verified": True,
        },
        "release_backend": {
            "version": 1, "channels": 0, "releases": 0, "head_set_sha256": "a" * 64,
            "cross_process_locking": True, "lock_backend": "fcntl", "verified": True,
        },
        "transition_receipts": {
            "version": 1, "receipts": 0, "head_sha256": "",
            "cross_process_locking": True, "lock_backend": "fcntl", "verified": True,
        },
        "evidence_gaps": [], "evidence_gap_count": 0, "verified": True,
    }


def _evaluate(deployments):
    operations = {
        "audit_sequence": 0,
        "audit_head": None,
        "audit_health": {"cross_process_locking": True, "verified": True, "lock_backend": "fcntl"},
        "outbox_capacity_remaining": 128,
        "outbox_health": {
            "cross_process_locking": True, "leased_intent_factory": True, "lock_backend": "fcntl",
            "sequence_meta_version": 1, "next_sequence": 1,
        },
        "deployments": deployments,
    }
    return evaluate_assurance(
        lifecycle=[], operations=operations,
        executor_bindings=[{"name": "query", "effect_class": "query", "replay_safe": True}],
        executor_coverage={"coverage_pct": 75.0}, receipt_stats={"version": 2},
        readiness={"ready_pct": 75.0, "policy_gaps": 0, "unsafe_actions": 0},
    )


def test_healthy_empty_deployment_state_satisfies_all_hard_invariants():
    report = _evaluate(_deployment_status())
    deployment_rows = [row for row in report.invariants if row.id.startswith("deployment.")]
    assert len(deployment_rows) == 5
    assert all(row.passed for row in deployment_rows)
    assert report.hard_failures == 0


def test_consumed_but_unreleased_evidence_gap_blocks_assurance():
    status = _deployment_status()
    status["verified"] = False
    status["evidence_gap_count"] = 1
    status["evidence_gaps"] = [{"kind": "consumption_without_release"}]
    report = _evaluate(status)
    assert report.posture == "blocked"
    assert any(row.id == "deployment.evidence-complete" and not row.passed for row in report.invariants)


def test_release_receipt_cardinality_mismatch_blocks_even_if_summary_claims_verified():
    status = _deployment_status()
    status["release_backend"]["releases"] = 1
    report = _evaluate(status)
    assert report.posture == "blocked"
    assert any(row.id == "deployment.release-receipt-cardinality" and not row.passed for row in report.invariants)


def test_any_deployment_ledger_integrity_failure_blocks():
    for section, invariant_id in (
        ("authorization", "deployment.authorization-ledger-coherent"),
        ("release_backend", "deployment.release-ledger-coherent"),
        ("transition_receipts", "deployment.transition-receipts-coherent"),
    ):
        status = deepcopy(_deployment_status())
        status[section]["verified"] = False
        report = _evaluate(status)
        assert report.posture == "blocked"
        assert any(row.id == invariant_id and not row.passed for row in report.invariants)
