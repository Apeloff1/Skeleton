from core.system_assurance import evaluate_assurance


def _base_operations(trust):
    return {
        "audit_sequence": 0,
        "audit_head": None,
        "audit_health": {"cross_process_locking": True, "verified": True, "lock_backend": "fcntl"},
        "outbox_capacity_remaining": 128,
        "outbox_health": {
            "cross_process_locking": True, "leased_intent_factory": True, "lock_backend": "fcntl",
            "sequence_meta_version": 1, "next_sequence": 1,
        },
        "epistemic_trust": trust,
    }


def _trust(*, required=False, finalized=False, quorum_capable=False, witness_healthy=True, finality_healthy=True):
    return {
        "integrity_healthy": witness_healthy and finality_healthy,
        "finality_satisfied": finalized,
        "policy": {
            "configured": quorum_capable, "configured_independence_groups": 3 if quorum_capable else 0,
            "required_groups": 3, "max_age_seconds": 3600,
            "quorum_capable": quorum_capable, "finality_required": required,
        },
        "witnesses": {
            "healthy": witness_healthy, "cross_process_locking": True, "lock_backend": "fcntl",
            "equivocations": 0,
        },
        "finality": {
            "verified": finality_healthy, "cross_process_locking": True, "lock_backend": "fcntl",
        },
        "current_head": {"finalized": finalized},
    }


def _evaluate(trust):
    return evaluate_assurance(
        lifecycle=[], operations=_base_operations(trust),
        executor_bindings=[{"name": "query", "effect_class": "query", "replay_safe": True}],
        executor_coverage={"coverage_pct": 75.0},
        receipt_stats={"version": 2},
        readiness={"ready_pct": 75.0, "policy_gaps": 0, "unsafe_actions": 0},
    )


def test_optional_unfinalized_trust_degrades_without_hard_failure():
    report = _evaluate(_trust(required=False, finalized=False, quorum_capable=False))
    assert report.hard_failures == 0
    assert report.posture == "degraded"
    failed_warnings = {x.id for x in report.invariants if x.severity == "warning" and not x.passed}
    assert {"truth.witness-quorum-capable", "truth.current-head-finalized"} <= failed_warnings


def test_required_finality_and_missing_quorum_block_system_assurance():
    report = _evaluate(_trust(required=True, finalized=False, quorum_capable=False))
    assert report.posture == "blocked"
    failed_hard = {x.id for x in report.invariants if x.severity == "hard" and not x.passed}
    assert {"truth.witness-quorum-capable", "truth.current-head-finalized"} <= failed_hard


def test_required_finalized_quorum_passes_trust_invariants():
    report = _evaluate(_trust(required=True, finalized=True, quorum_capable=True))
    trust_rows = [x for x in report.invariants if x.id.startswith("truth.")]
    assert all(x.passed for x in trust_rows)
    assert report.hard_failures == 0


def test_witness_or_finality_integrity_failure_blocks_even_when_finality_is_optional():
    witness_failure = _evaluate(_trust(witness_healthy=False))
    assert witness_failure.posture == "blocked"
    assert any(x.id == "truth.witness-ledger-coherent" and not x.passed for x in witness_failure.invariants)

    finality_failure = _evaluate(_trust(finality_healthy=False))
    assert finality_failure.posture == "blocked"
    assert any(x.id == "truth.finality-ledger-coherent" and not x.passed for x in finality_failure.invariants)
