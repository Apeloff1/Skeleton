from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.mesh.batching_autoscaling import (
    BatchingAutoscalingError,
    ServiceObjectiveObservation,
    ServiceObjectivePolicy,
    qualify_autoscaling,
)
from skeleton.network.model_placement import ModelPlacementDecision
from skeleton.shells.worker_scaling import ScalingAction


NOW = 200.0


def _placement(*, accepted: bool = True) -> ModelPlacementDecision:
    return ModelPlacementDecision(
        accepted=accepted,
        reasons=() if accepted else ("forced-rejection",),
        request_digest="a" * 64,
        selected_worker_id="worker-a" if accepted else None,
        selected_worker_generation=1 if accepted else None,
        selected_worker_identity_digest="b" * 64 if accepted else None,
        warm_authorization_digest="c" * 64 if accepted else None,
        warm_observation_digest="d" * 64 if accepted else None,
        reservation_digest="e" * 64 if accepted else None,
        candidate_worker_ids=("worker-a",) if accepted else (),
        rejected=(),
        topology_digest="f" * 64,
        capacity_digest="1" * 64,
    )


def _policy(**overrides: object) -> ServiceObjectivePolicy:
    values: dict[str, object] = {
        "policy_id": "slo-v1",
        "target_p99_latency_ms": 250.0,
        "max_cancellation_rate": 0.02,
        "max_error_rate": 0.01,
        "min_quality_score": 0.90,
        "observation_max_age_s": 30.0,
        "target_queue_per_worker": 10.0,
        "scale_out_queue_per_worker": 25.0,
        "scale_in_queue_per_worker": 2.0,
        "min_workers": 2,
        "max_workers": 20,
        "max_scale_step": 4,
    }
    values.update(overrides)
    return ServiceObjectivePolicy(**values)


def _observation(
    placement: ModelPlacementDecision,
    **overrides: object,
) -> ServiceObjectiveObservation:
    values: dict[str, object] = {
        "window_id": "window-1",
        "placement_decision_digest": placement.decision_digest,
        "sample_count": 1000,
        "healthy_workers": 4,
        "queued": 40,
        "p50_latency_ms": 80.0,
        "p95_latency_ms": 150.0,
        "p99_latency_ms": 200.0,
        "cancellation_rate": 0.01,
        "error_rate": 0.005,
        "quality_score": 0.95,
        "observed_at": 190.0,
        "evidence_refs": (
            EvidenceRef(
                source="metrics://inference/window-1",
                digest="2" * 64,
                category="service_objective",
            ),
        ),
        "verifier_id": "verifier:slo",
        "verifier_digest": "3" * 64,
        "independent": True,
    }
    values.update(overrides)
    return ServiceObjectiveObservation(**values)


def test_queue_pressure_scales_out_within_bounds() -> None:
    placement = _placement()
    decision = qualify_autoscaling(
        placement_decision=placement,
        observation=_observation(
            placement,
            queued=120,
        ),
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.accepted is True
    assert decision.action is ScalingAction.SCALE_OUT
    assert 4 < decision.desired_workers <= 8
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "inference_autoscaling"
    assert evidence.digest == decision.decision_digest


@pytest.mark.parametrize(
    "overrides",
    (
        {"p99_latency_ms": 300.0},
        {"cancellation_rate": 0.05},
        {"error_rate": 0.05},
    ),
)
def test_service_objective_stress_forces_scale_out(
    overrides: dict[str, object],
) -> None:
    placement = _placement()
    observation = _observation(
        placement,
        queued=0,
        **overrides,
    )
    decision = qualify_autoscaling(
        placement_decision=placement,
        observation=observation,
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.accepted is True
    assert decision.action is ScalingAction.SCALE_OUT
    assert decision.desired_workers == 8


def test_quality_regression_is_not_treated_as_capacity_problem() -> None:
    placement = _placement()
    decision = qualify_autoscaling(
        placement_decision=placement,
        observation=_observation(
            placement,
            quality_score=0.80,
            queued=120,
        ),
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert "quality-budget-breached" in decision.reasons
    with pytest.raises(
        BatchingAutoscalingError,
        match="rejected autoscaling",
    ):
        decision.accepted_evidence_ref()


def test_scale_in_only_when_all_service_objectives_are_healthy() -> None:
    placement = _placement()
    healthy = qualify_autoscaling(
        placement_decision=placement,
        observation=_observation(
            placement,
            healthy_workers=8,
            queued=0,
            p99_latency_ms=150.0,
            cancellation_rate=0.0,
            error_rate=0.0,
            quality_score=0.98,
        ),
        policy=_policy(),
        observed_at=NOW,
    )
    assert healthy.accepted is True
    assert healthy.action is ScalingAction.SCALE_IN
    assert healthy.desired_workers == 4


def test_breach_at_max_workers_fails_closed() -> None:
    placement = _placement()
    decision = qualify_autoscaling(
        placement_decision=placement,
        observation=_observation(
            placement,
            healthy_workers=20,
            queued=500,
            p99_latency_ms=500.0,
        ),
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert "service-objective-breach-at-max-workers" in decision.reasons
    assert decision.action is ScalingAction.HOLD


def test_stale_or_future_observation_is_rejected() -> None:
    placement = _placement()
    stale = qualify_autoscaling(
        placement_decision=placement,
        observation=_observation(
            placement,
            observed_at=100.0,
        ),
        policy=_policy(observation_max_age_s=30.0),
        observed_at=NOW,
    )
    assert stale.accepted is False
    assert "observation-stale" in stale.reasons

    future = qualify_autoscaling(
        placement_decision=placement,
        observation=_observation(
            placement,
            observed_at=201.0,
        ),
        policy=_policy(),
        observed_at=NOW,
    )
    assert future.accepted is False
    assert "observation-not-yet-valid" in future.reasons


def test_observation_must_bind_exact_dist02_placement() -> None:
    placement = _placement()
    decision = qualify_autoscaling(
        placement_decision=placement,
        observation=_observation(
            placement,
            placement_decision_digest="0" * 64,
        ),
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert "observation-placement-mismatch" in decision.reasons


def test_rejected_placement_blocks_scaling_authority() -> None:
    rejected = _placement(accepted=False)
    decision = qualify_autoscaling(
        placement_decision=rejected,
        observation=_observation(rejected),
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert "placement-decision-rejected" in decision.reasons


def test_service_objective_observation_must_be_independent() -> None:
    placement = _placement()
    with pytest.raises(
        BatchingAutoscalingError,
        match="must be independent",
    ):
        _observation(placement, independent=False)


def test_latency_percentiles_must_be_monotonic() -> None:
    placement = _placement()
    with pytest.raises(
        BatchingAutoscalingError,
        match="percentiles must be monotonic",
    ):
        _observation(
            placement,
            p50_latency_ms=200.0,
            p95_latency_ms=150.0,
        )


def test_decision_identity_changes_with_bound_observation() -> None:
    placement = _placement()
    first = qualify_autoscaling(
        placement_decision=placement,
        observation=_observation(placement, queued=120),
        policy=_policy(),
        observed_at=NOW,
    )
    second = qualify_autoscaling(
        placement_decision=placement,
        observation=_observation(
            placement,
            window_id="window-2",
            queued=120,
        ),
        policy=_policy(),
        observed_at=NOW,
    )

    assert first.accepted is True
    assert second.accepted is True
    assert first.decision_digest != second.decision_digest
