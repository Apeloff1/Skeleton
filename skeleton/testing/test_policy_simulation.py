from __future__ import annotations

import pytest

from skeleton.ai.runtime.security.policy_simulation import (
    PolicyDelta,
    PolicySimulation,
    PolicySimulationError,
    PolicyTrace,
    simulate_policy_change,
)


def _trace(
    trace_id: str,
    decision: str,
    *,
    subject: str = "tenant-a",
    workload: str = "assistant",
) -> PolicyTrace:
    return PolicyTrace(
        trace_id=trace_id,
        subject_id=subject,
        workload_id=workload,
        decision=decision,
    )


def test_policy_simulation_reports_deltas_and_affected_scope() -> None:
    baseline = (
        _trace("t-1", "allow", subject="tenant-a", workload="assistant"),
        _trace("t-2", "deny", subject="tenant-b", workload="tool-runtime"),
        _trace("t-3", "abstain", subject="tenant-c", workload="retrieval"),
    )
    candidate = (
        _trace("t-1", "deny", subject="tenant-a", workload="assistant"),
        _trace("t-2", "abstain", subject="tenant-b", workload="tool-runtime"),
        _trace("t-3", "abstain", subject="tenant-c", workload="retrieval"),
    )

    receipt = simulate_policy_change(
        simulation_id="sim-vol166-001",
        baseline_policy_id="policy-v1",
        candidate_policy_id="policy-v2",
        baseline_traces=baseline,
        candidate_traces=candidate,
    )

    assert receipt.total_traces == 3
    assert receipt.changed_traces == 2
    assert dict(receipt.transition_counts) == {
        "allow->deny": 1,
        "deny->abstain": 1,
    }
    assert receipt.affected_subjects == ("tenant-a", "tenant-b")
    assert receipt.affected_workloads == ("assistant", "tool-runtime")
    assert [delta.trace_id for delta in receipt.deltas] == ["t-1", "t-2"]
    assert receipt.production_authority is False
    assert receipt.external_side_effects is False
    assert len(receipt.digest) == 64


def test_policy_simulation_is_deterministic_across_input_order() -> None:
    baseline = (
        _trace("t-2", "deny", subject="b"),
        _trace("t-1", "allow", subject="a"),
    )
    candidate = (
        _trace("t-1", "deny", subject="a"),
        _trace("t-2", "allow", subject="b"),
    )

    first = simulate_policy_change(
        simulation_id="sim-deterministic",
        baseline_policy_id="policy-v1",
        candidate_policy_id="policy-v2",
        baseline_traces=baseline,
        candidate_traces=candidate,
    )
    second = simulate_policy_change(
        simulation_id="sim-deterministic",
        baseline_policy_id="policy-v1",
        candidate_policy_id="policy-v2",
        baseline_traces=reversed(baseline),
        candidate_traces=reversed(candidate),
    )

    assert first == second
    assert first.digest == second.digest
    assert [delta.trace_id for delta in first.deltas] == ["t-1", "t-2"]


def test_policy_simulation_rejects_missing_candidate_trace() -> None:
    with pytest.raises(PolicySimulationError, match="exact same trace IDs"):
        simulate_policy_change(
            simulation_id="sim-missing",
            baseline_policy_id="policy-v1",
            candidate_policy_id="policy-v2",
            baseline_traces=(_trace("t-1", "allow"), _trace("t-2", "deny")),
            candidate_traces=(_trace("t-1", "deny"),),
        )


def test_policy_simulation_rejects_duplicate_trace_ids() -> None:
    with pytest.raises(PolicySimulationError, match="trace IDs must be unique"):
        simulate_policy_change(
            simulation_id="sim-duplicate",
            baseline_policy_id="policy-v1",
            candidate_policy_id="policy-v2",
            baseline_traces=(
                _trace("t-1", "allow"),
                _trace("t-1", "deny"),
            ),
            candidate_traces=(_trace("t-1", "deny"),),
        )


def test_policy_simulation_rejects_subject_or_workload_identity_drift() -> None:
    with pytest.raises(PolicySimulationError, match="identity drifted"):
        simulate_policy_change(
            simulation_id="sim-drift",
            baseline_policy_id="policy-v1",
            candidate_policy_id="policy-v2",
            baseline_traces=(
                _trace("t-1", "allow", subject="tenant-a", workload="assistant"),
            ),
            candidate_traces=(
                _trace("t-1", "deny", subject="tenant-b", workload="assistant"),
            ),
        )


def test_policy_trace_rejects_unknown_decision() -> None:
    with pytest.raises(PolicySimulationError, match="allow, deny, or abstain"):
        _trace("t-1", "audit")


def test_policy_delta_requires_actual_change() -> None:
    with pytest.raises(PolicySimulationError, match="changed decision"):
        PolicyDelta(
            trace_id="t-1",
            subject_id="tenant-a",
            workload_id="assistant",
            baseline_decision="deny",
            candidate_decision="deny",
        )


def test_policy_simulation_cannot_grant_authority_or_side_effects() -> None:
    common = dict(
        simulation_id="sim-authority",
        baseline_policy_id="policy-v1",
        candidate_policy_id="policy-v2",
        baseline_trace_digest="a" * 64,
        candidate_trace_digest="b" * 64,
        total_traces=0,
        deltas=(),
        transition_counts={},
        affected_subjects=(),
        affected_workloads=(),
    )
    with pytest.raises(PolicySimulationError, match="production authority"):
        PolicySimulation(**common, production_authority=True)
    with pytest.raises(PolicySimulationError, match="external side effects"):
        PolicySimulation(**common, external_side_effects=True)


def test_transition_counts_are_immutable() -> None:
    receipt = simulate_policy_change(
        simulation_id="sim-immutable",
        baseline_policy_id="policy-v1",
        candidate_policy_id="policy-v2",
        baseline_traces=(_trace("t-1", "allow"),),
        candidate_traces=(_trace("t-1", "deny"),),
    )

    with pytest.raises(TypeError):
        receipt.transition_counts["allow->deny"] = 99  # type: ignore[index]


def test_policy_simulation_rejects_forged_transition_summary() -> None:
    delta = PolicyDelta(
        trace_id="t-1",
        subject_id="tenant-a",
        workload_id="assistant",
        baseline_decision="allow",
        candidate_decision="deny",
    )
    with pytest.raises(PolicySimulationError, match="transition counts"):
        PolicySimulation(
            simulation_id="sim-forged-count",
            baseline_policy_id="policy-v1",
            candidate_policy_id="policy-v2",
            baseline_trace_digest="a" * 64,
            candidate_trace_digest="b" * 64,
            total_traces=1,
            deltas=(delta,),
            transition_counts={"deny->allow": 1},
            affected_subjects=("tenant-a",),
            affected_workloads=("assistant",),
        )


def test_policy_simulation_rejects_forged_affected_scope() -> None:
    delta = PolicyDelta(
        trace_id="t-1",
        subject_id="tenant-a",
        workload_id="assistant",
        baseline_decision="allow",
        candidate_decision="deny",
    )
    with pytest.raises(PolicySimulationError, match="affected subjects"):
        PolicySimulation(
            simulation_id="sim-forged-scope",
            baseline_policy_id="policy-v1",
            candidate_policy_id="policy-v2",
            baseline_trace_digest="a" * 64,
            candidate_trace_digest="b" * 64,
            total_traces=1,
            deltas=(delta,),
            transition_counts={"allow->deny": 1},
            affected_subjects=("tenant-b",),
            affected_workloads=("assistant",),
        )


def test_policy_simulation_rejects_invalid_trace_digest() -> None:
    with pytest.raises(PolicySimulationError, match="sha256"):
        PolicySimulation(
            simulation_id="sim-bad-digest",
            baseline_policy_id="policy-v1",
            candidate_policy_id="policy-v2",
            baseline_trace_digest="not-a-digest",
            candidate_trace_digest="b" * 64,
            total_traces=0,
            deltas=(),
            transition_counts={},
            affected_subjects=(),
            affected_workloads=(),
        )
