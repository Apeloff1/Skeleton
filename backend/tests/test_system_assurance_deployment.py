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
        "evidence_checkpoint": {
            "version": 2,
            "authorization_head_sha256": "e" * 64,
            "authorization_events": 0,
            "receipt_head_sha256": "f" * 64,
            "receipt_events": 0,
            "release_channels": [],
            "completed_releases": 0,
            "fully_portable_releases": 0,
            "evidence_gap_count": 0,
            "release_channels_sha256": "9" * 64,
            "root_sha256": "b" * 64,
            "attestation_sha256": "c" * 64,
        },
        "checkpoint_publication": {
            "version": 1,
            "publications": 1,
            "head_sha256": "d" * 64,
            "checkpoint_root_sha256": "b" * 64,
            "checkpoint_attestation_sha256": "c" * 64,
            "latest_published_at": "2026-09-14T12:00:00+00:00",
            "verified": True,
            "cross_process_locking": True,
            "lock_backend": "fcntl",
        },
        "checkpoint_current": True,
        "externally_pinnable": True,
        "independently_verifiable": True,
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
    assert len(deployment_rows) == 9
    assert all(row.passed for row in deployment_rows)
    assert report.hard_failures == 0


def test_consumed_but_unreleased_evidence_gap_blocks_assurance():
    status = _deployment_status()
    status["verified"] = False
    status["evidence_gap_count"] = 1
    status["evidence_gaps"] = [{"kind": "consumption_without_release"}]
    status["checkpoint_current"] = False
    status["externally_pinnable"] = False
    report = _evaluate(status)
    assert report.posture == "blocked"
    assert any(row.id == "deployment.evidence-complete" and not row.passed for row in report.invariants)
    assert any(row.id == "deployment.checkpoint-current" and not row.passed for row in report.invariants)


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
        ("checkpoint_publication", "deployment.checkpoint-ledger-coherent"),
    ):
        status = deepcopy(_deployment_status())
        status[section]["verified"] = False
        report = _evaluate(status)
        assert report.posture == "blocked"
        assert any(row.id == invariant_id and not row.passed for row in report.invariants)


def test_stale_checkpoint_root_blocks_even_if_summary_boolean_claims_current():
    status = _deployment_status()
    status["checkpoint_publication"]["checkpoint_root_sha256"] = "8" * 64
    report = _evaluate(status)

    assert report.posture == "blocked"
    assert any(row.id == "deployment.checkpoint-current" and not row.passed for row in report.invariants)
    assert any(row.id == "deployment.externally-pinnable" and not row.passed for row in report.invariants)


def test_external_pinnability_is_independent_hard_requirement():
    status = _deployment_status()
    status["externally_pinnable"] = False
    report = _evaluate(status)

    assert report.posture == "blocked"
    assert any(row.id == "deployment.externally-pinnable" and not row.passed for row in report.invariants)


def test_checkpoint_shape_rejects_boolean_event_count_type_confusion():
    for key in ("authorization_events", "receipt_events"):
        status = deepcopy(_deployment_status())
        status["evidence_checkpoint"][key] = True
        report = _evaluate(status)
        assert report.posture == "blocked"
        assert any(row.id == "deployment.checkpoint-verifiable" and not row.passed for row in report.invariants)


def test_deployment_summary_counts_reject_python_coercion():
    for section, key in ((None, "evidence_gap_count"), ("release_backend", "releases"), ("transition_receipts", "receipts")):
        status = deepcopy(_deployment_status())
        if section is None:
            status[key] = "0"
        else:
            status[section][key] = True
        report = _evaluate(status)
        assert report.posture == "blocked"
        assert any(row.id in {"deployment.evidence-complete", "deployment.release-receipt-cardinality"}
                   and not row.passed for row in report.invariants)
