from dataclasses import replace

from core.system_assurance import evaluate_assurance, verify_assurance


def _base(**overrides):
    data = {
        "lifecycle": [],
        "operations": {"audit_sequence": 0, "audit_head": None, "outbox_capacity_remaining": 128},
        "executor_bindings": [
            {"name": "state", "effect_class": "state", "replay_safe": True},
            {"name": "query", "effect_class": "query", "replay_safe": True},
        ],
        "executor_coverage": {"coverage_pct": 61.9},
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


def test_native_coverage_below_majority_degrades_but_does_not_block():
    report = evaluate_assurance(**_base(executor_coverage={"coverage_pct": 47.6}))
    assert report.posture == "degraded"
    assert report.hard_failures == 0
    assert report.warnings == 1


def test_evidence_gap_is_hard_failure():
    report = evaluate_assurance(**_base(lifecycle=[{"state": "evidence_gap", "anomalies": ("executed_without_receipt",)}]))
    assert report.posture == "blocked"
    assert report.hard_failures >= 1


def test_zero_queue_capacity_blocks_assurance():
    report = evaluate_assurance(**_base(operations={"audit_sequence": 0, "audit_head": None, "outbox_capacity_remaining": 0}))
    assert report.posture == "blocked"
    assert any(item.id == "queue.capacity" and not item.passed for item in report.invariants)


def test_state_executor_without_replay_safety_blocks():
    report = evaluate_assurance(**_base(executor_bindings=[
        {"name": "unsafe", "effect_class": "state", "replay_safe": False},
    ]))
    assert report.posture == "blocked"
    assert any(item.id == "executors.replay-safe-effects" and not item.passed for item in report.invariants)


def test_query_executor_need_not_claim_replay_safety_for_effect_invariant():
    report = evaluate_assurance(**_base(executor_bindings=[
        {"name": "query", "effect_class": "query", "replay_safe": False},
    ]))
    assert not any(item.id == "executors.replay-safe-effects" and not item.passed for item in report.invariants)


def test_missing_audit_head_with_nonzero_sequence_blocks():
    report = evaluate_assurance(**_base(operations={"audit_sequence": 4, "audit_head": None, "outbox_capacity_remaining": 128}))
    assert report.posture == "blocked"


def test_attestation_detects_report_mutation():
    report = evaluate_assurance(**_base())
    mutated = replace(report, native_coverage_pct=99.9)
    assert verify_assurance(mutated) is False
