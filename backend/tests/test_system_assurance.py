from dataclasses import replace

from core.system_assurance import evaluate_assurance, verify_assurance


def _operations(**overrides):
    value = {
        "audit_sequence": 0,
        "audit_head": None,
        "outbox_capacity_remaining": 128,
        "outbox_health": {
            "cross_process_locking": True,
            "lock_backend": "fcntl",
            "sequence_meta_version": 1,
            "next_sequence": 1,
        },
    }
    value.update(overrides)
    return value


def _base(**overrides):
    data = {
        "lifecycle": [],
        "operations": _operations(),
        "executor_bindings": [
            {"name": "state", "effect_class": "state", "replay_safe": True},
            {"name": "query", "effect_class": "query", "replay_safe": True},
        ],
        "executor_coverage": {"coverage_pct": 61.9},
        "readiness": {"ready_pct": 61.9, "policy_gaps": 0, "unsafe_actions": 0},
        "receipt_stats": {"version": 2},
    }
    data.update(overrides)
    return data


def test_healthy_report_requires_all_hard_invariants_and_warning_targets():
    report = evaluate_assurance(**_base())
    assert report.posture == "healthy"
    assert report.hard_failures == 0
    assert report.warnings == 0
    assert verify_assurance(report) is True
    assert len(report.attestation_sha256) == 64


def test_readiness_below_majority_degrades_but_does_not_block():
    report = evaluate_assurance(**_base(readiness={"ready_pct": 47.6, "policy_gaps": 0, "unsafe_actions": 0}))
    assert report.posture == "degraded"
    assert report.hard_failures == 0
    assert report.warnings == 1


def test_evidence_gap_is_hard_failure():
    report = evaluate_assurance(**_base(lifecycle=[{"state": "evidence_gap", "anomalies": ("executed_without_receipt",)}]))
    assert report.posture == "blocked"
    assert report.hard_failures >= 1


def test_zero_queue_capacity_blocks_assurance():
    report = evaluate_assurance(**_base(operations=_operations(outbox_capacity_remaining=0)))
    assert report.posture == "blocked"
    assert any(item.id == "queue.capacity" and not item.passed for item in report.invariants)


def test_thread_only_outbox_blocks_assurance():
    health = dict(_operations()["outbox_health"])
    health["cross_process_locking"] = False
    report = evaluate_assurance(**_base(operations=_operations(outbox_health=health)))
    assert report.posture == "blocked"
    assert any(item.id == "queue.cross-process-coherence" and not item.passed for item in report.invariants)


def test_missing_sequence_metadata_blocks_assurance():
    health = dict(_operations()["outbox_health"])
    health["sequence_meta_version"] = 0
    report = evaluate_assurance(**_base(operations=_operations(outbox_health=health)))
    assert report.posture == "blocked"
    assert any(item.id == "queue.monotonic-sequence" and not item.passed for item in report.invariants)


def test_state_executor_without_replay_safety_blocks():
    report = evaluate_assurance(**_base(executor_bindings=[{"name": "unsafe", "effect_class": "state", "replay_safe": False}]))
    assert report.posture == "blocked"
    assert any(item.id == "executors.replay-safe-effects" and not item.passed for item in report.invariants)


def test_query_executor_need_not_claim_replay_safety_for_effect_invariant():
    report = evaluate_assurance(**_base(executor_bindings=[{"name": "query", "effect_class": "query", "replay_safe": False}]))
    assert not any(item.id == "executors.replay-safe-effects" and not item.passed for item in report.invariants)


def test_missing_audit_head_with_nonzero_sequence_blocks():
    report = evaluate_assurance(**_base(operations=_operations(audit_sequence=4, audit_head=None)))
    assert report.posture == "blocked"


def test_policy_gap_blocks_even_when_executor_coverage_is_high():
    report = evaluate_assurance(**_base(readiness={"ready_pct": 95.0, "policy_gaps": 1, "unsafe_actions": 0}))
    assert report.posture == "blocked"
    assert any(item.id == "convergence.policy-complete" and not item.passed for item in report.invariants)


def test_attestation_detects_report_mutation():
    report = evaluate_assurance(**_base())
    mutated = replace(report, readiness_pct=99.9)
    assert verify_assurance(mutated) is False
