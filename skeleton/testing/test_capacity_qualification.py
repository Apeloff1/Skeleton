from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.mesh.batching_autoscaling import AutoscalingDecision
from skeleton.mesh.capacity_qualification import (
    CapacityDisposition,
    CapacityObservation,
    CapacityQualificationError,
    LoadCapacityProfile,
    qualify_capacity,
)
from skeleton.shells.worker_scaling import ScalingAction


NOW = 1_800_000_000.0


def _profile(**overrides: object) -> LoadCapacityProfile:
    values: dict[str, object] = {
        "profile_id": "dist-04-ci",
        "max_workers": 4,
        "max_queue_depth": 100,
        "target_p99_latency_ms": 500.0,
        "max_error_rate": 0.05,
        "max_cancellation_rate": 0.02,
        "max_measured_cost_usd": 10.0,
        "max_cost_reconciliation_error_usd": 0.05,
        "observation_max_age_s": 60.0,
    }
    values.update(overrides)
    return LoadCapacityProfile(**values)


def _autoscaling(
    *,
    current_workers: int = 2,
    desired_workers: int = 2,
    action: ScalingAction = ScalingAction.HOLD,
    accepted: bool = True,
) -> AutoscalingDecision:
    return AutoscalingDecision(
        accepted=accepted,
        reasons=() if accepted else ("forced-rejection",),
        action=action,
        current_workers=current_workers,
        desired_workers=desired_workers,
        placement_decision_digest="1" * 64,
        observation_digest="2" * 64,
        policy_digest="3" * 64,
    )


def _observation(
    profile: LoadCapacityProfile,
    autoscaling: AutoscalingDecision,
    **overrides: object,
) -> CapacityObservation:
    values: dict[str, object] = {
        "profile_digest": profile.profile_digest,
        "autoscaling_decision_digest": autoscaling.decision_digest,
        "observed_at": NOW - 5.0,
        "healthy_workers": autoscaling.current_workers,
        "queue_depth": 10,
        "p99_latency_ms": 100.0,
        "error_rate": 0.0,
        "cancellation_rate": 0.0,
        "offered_requests": 100,
        "completed_requests": 100,
        "rejected_requests": 0,
        "shed_requests": 0,
        "partition_events": 0,
        "stale_worker_commits": 0,
        "measured_cost_usd": 1.0,
        "accounted_cost_usd": 1.0,
        "evidence_refs": (
            EvidenceRef(
                source="load://dist-04/independent",
                digest="4" * 64,
                category="load",
            ),
        ),
        "independent": True,
    }
    values.update(overrides)
    return CapacityObservation(**values)


def test_healthy_capacity_qualifies() -> None:
    profile = _profile()
    autoscaling = _autoscaling()
    observation = _observation(profile, autoscaling)

    decision = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=observation,
        observed_at=NOW,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.disposition is CapacityDisposition.HEALTHY
    assert decision.queue_utilization == pytest.approx(0.1)
    assert decision.cost_reconciliation_error_usd == 0.0
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "capacity_qualification"
    assert evidence.digest == decision.decision_digest


def test_degraded_capacity_requires_scale_out_below_max() -> None:
    profile = _profile()
    scale_out = _autoscaling(
        current_workers=2,
        desired_workers=4,
        action=ScalingAction.SCALE_OUT,
    )
    observation = _observation(
        profile,
        scale_out,
        queue_depth=101,
        completed_requests=90,
        shed_requests=10,
    )
    accepted = qualify_capacity(
        profile=profile,
        autoscaling_decision=scale_out,
        observation=observation,
        observed_at=NOW,
    )
    assert accepted.accepted is True
    assert accepted.disposition is CapacityDisposition.DEGRADED

    hold = _autoscaling(
        current_workers=2,
        desired_workers=2,
        action=ScalingAction.HOLD,
    )
    rejected = qualify_capacity(
        profile=profile,
        autoscaling_decision=hold,
        observation=_observation(
            profile,
            hold,
            queue_depth=101,
            completed_requests=90,
            shed_requests=10,
        ),
        observed_at=NOW,
    )
    assert rejected.accepted is False
    assert "capacity-pressure-without-scale-out" in rejected.reasons


def test_saturation_at_max_requires_controlled_shedding() -> None:
    profile = _profile()
    autoscaling = _autoscaling(
        current_workers=4,
        desired_workers=4,
        action=ScalingAction.HOLD,
    )
    accepted = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=_observation(
            profile,
            autoscaling,
            queue_depth=120,
            completed_requests=90,
            shed_requests=10,
        ),
        observed_at=NOW,
    )
    assert accepted.accepted is True
    assert accepted.disposition is CapacityDisposition.SATURATED

    rejected = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=_observation(
            profile,
            autoscaling,
            queue_depth=120,
        ),
        observed_at=NOW,
    )
    assert rejected.accepted is False
    assert "saturation-without-load-shedding" in rejected.reasons


def test_scale_in_is_forbidden_under_capacity_pressure() -> None:
    profile = _profile()
    autoscaling = _autoscaling(
        current_workers=3,
        desired_workers=2,
        action=ScalingAction.SCALE_IN,
    )
    decision = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=_observation(
            profile,
            autoscaling,
            p99_latency_ms=700.0,
            completed_requests=95,
            shed_requests=5,
        ),
        observed_at=NOW,
    )
    assert decision.accepted is False
    assert "scale-in-under-capacity-pressure" in decision.reasons
    assert "capacity-pressure-without-scale-out" in decision.reasons


def test_partition_with_stale_worker_commit_fails_closed() -> None:
    profile = _profile()
    autoscaling = _autoscaling(
        current_workers=4,
        desired_workers=4,
    )
    decision = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=_observation(
            profile,
            autoscaling,
            partition_events=1,
            stale_worker_commits=1,
        ),
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert "stale-worker-commit-detected" in decision.reasons
    assert "partition-stale-worker-commit" in decision.reasons


def test_request_accounting_must_reconcile_exactly() -> None:
    profile = _profile()
    autoscaling = _autoscaling()
    decision = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=_observation(
            profile,
            autoscaling,
            completed_requests=99,
        ),
        observed_at=NOW,
    )
    assert decision.accepted is False
    assert "request-accounting-divergence" in decision.reasons


def test_cost_budget_and_reconciliation_are_promotion_blocking() -> None:
    profile = _profile()
    autoscaling = _autoscaling()

    budget = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=_observation(
            profile,
            autoscaling,
            measured_cost_usd=11.0,
            accounted_cost_usd=11.0,
        ),
        observed_at=NOW,
    )
    assert budget.accepted is False
    assert "measured-cost-budget-exceeded" in budget.reasons

    drift = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=_observation(
            profile,
            autoscaling,
            measured_cost_usd=1.0,
            accounted_cost_usd=1.2,
        ),
        observed_at=NOW,
    )
    assert drift.accepted is False
    assert "cost-reconciliation-divergence" in drift.reasons


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("profile", "load-profile-digest-mismatch"),
        ("autoscaling", "autoscaling-decision-digest-mismatch"),
        ("future", "observation-not-yet-valid"),
        ("stale", "observation-stale"),
        ("workers", "healthy-worker-count-mismatch"),
    ),
)
def test_identity_and_freshness_drift_fail_closed(
    mutation: str,
    reason: str,
) -> None:
    profile = _profile()
    autoscaling = _autoscaling()
    observation = _observation(profile, autoscaling)

    if mutation == "profile":
        observation = replace(observation, profile_digest="0" * 64)
    elif mutation == "autoscaling":
        observation = replace(
            observation,
            autoscaling_decision_digest="0" * 64,
        )
    elif mutation == "future":
        observation = replace(observation, observed_at=NOW + 1.0)
    elif mutation == "stale":
        observation = replace(observation, observed_at=NOW - 61.0)
    else:
        observation = replace(observation, healthy_workers=3)

    decision = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=observation,
        observed_at=NOW,
    )
    assert decision.accepted is False
    assert reason in decision.reasons


def test_rejected_autoscaling_blocks_capacity_qualification() -> None:
    profile = _profile()
    autoscaling = _autoscaling(accepted=False)
    decision = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=_observation(profile, autoscaling),
        observed_at=NOW,
    )
    assert decision.accepted is False
    assert "autoscaling-decision-rejected" in decision.reasons


def test_rejected_capacity_decision_cannot_be_promotion_evidence() -> None:
    profile = _profile()
    autoscaling = _autoscaling()
    decision = qualify_capacity(
        profile=profile,
        autoscaling_decision=autoscaling,
        observation=_observation(
            profile,
            autoscaling,
            completed_requests=99,
        ),
        observed_at=NOW,
    )
    assert decision.accepted is False
    with pytest.raises(
        CapacityQualificationError,
        match="cannot become promotion evidence",
    ):
        decision.accepted_evidence_ref()


def test_independent_evidence_is_mandatory() -> None:
    profile = _profile()
    autoscaling = _autoscaling()
    with pytest.raises(
        CapacityQualificationError,
        match="independently verified",
    ):
        _observation(
            profile,
            autoscaling,
            independent=False,
        )
