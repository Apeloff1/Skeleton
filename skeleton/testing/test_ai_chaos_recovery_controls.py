from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.reliability_release import (
    ChaosAuthority,
    ChaosCampaign,
    ChaosController,
    ChaosObservation,
    Fault,
    RecoveryDrill,
    RecoveryObjective,
)


def _campaign(**overrides: object) -> ChaosCampaign:
    values = {
        "campaign_id": "campaign-1",
        "faults": (Fault("fault-1", "retrieval", "latency", 5),),
        "rollback_ref": "runbook://retrieval/rollback",
        "hypothesis": "retrieval remains within SLO during bounded latency",
        "max_affected_targets": 1,
        "max_total_fault_seconds": 10,
    }
    values.update(overrides)
    return ChaosCampaign(**values)


def _authority(**overrides: object) -> ChaosAuthority:
    values = {
        "principal_id": "reliability-worker",
        "allowed_targets": ("retrieval",),
        "allowed_fault_kinds": ("latency",),
        "max_fault_seconds": 5,
    }
    values.update(overrides)
    return ChaosAuthority(**values)


def test_campaign_rejects_target_and_duration_blast_radius() -> None:
    with pytest.raises(ValueError, match="target blast radius"):
        _campaign(
            faults=(
                Fault("f1", "retrieval", "latency", 2),
                Fault("f2", "memory", "latency", 2),
            )
        )
    with pytest.raises(ValueError, match="fault-time budget"):
        _campaign(faults=(Fault("f1", "retrieval", "latency", 11),))


def test_authority_fails_closed_for_target_kind_and_duration() -> None:
    campaign = _campaign()
    with pytest.raises(PermissionError, match="target not authorized"):
        _authority(allowed_targets=("memory",)).authorize(campaign)
    with pytest.raises(PermissionError, match="kind not authorized"):
        _authority(allowed_fault_kinds=("loss",)).authorize(campaign)
    with pytest.raises(PermissionError, match="duration not authorized"):
        _authority(max_fault_seconds=4).authorize(campaign)


def test_controller_aborts_on_health_or_error_budget_boundary() -> None:
    campaign = _campaign()
    authority = _authority()
    controller = ChaosController(minimum_error_budget=0.25)

    healthy = controller.evaluate(
        campaign,
        authority,
        ChaosObservation("campaign-1", 1, True, 0.25),
    )
    assert healthy.decision == "continue"
    assert healthy.rollback_ref == campaign.rollback_ref
    assert len(healthy.digest) == 64

    unhealthy = ChaosController(minimum_error_budget=0.25).evaluate(
        campaign,
        authority,
        ChaosObservation("campaign-1", 1, False, 1.0),
    )
    assert unhealthy.decision == "abort"

    exhausted = ChaosController(minimum_error_budget=0.25).evaluate(
        campaign,
        authority,
        ChaosObservation("campaign-1", 1, True, 0.24),
    )
    assert exhausted.decision == "abort"


def test_controller_rejects_cross_campaign_observation() -> None:
    with pytest.raises(ValueError, match="campaign mismatch"):
        ChaosController().evaluate(
            _campaign(),
            _authority(),
            ChaosObservation("other", 1, True, 1.0),
        )


def test_campaign_digest_is_order_sensitive_and_evidence_bound() -> None:
    first = ChaosCampaign(
        "c",
        (Fault("a", "retrieval", "latency", 2), Fault("b", "retrieval", "latency", 3)),
        "rollback://one",
        max_total_fault_seconds=5,
    )
    second = ChaosCampaign(
        "c",
        (Fault("b", "retrieval", "latency", 3), Fault("a", "retrieval", "latency", 2)),
        "rollback://one",
        max_total_fault_seconds=5,
    )
    changed_runbook = ChaosCampaign(
        "c",
        first.faults,
        "rollback://two",
        max_total_fault_seconds=5,
    )
    assert first.digest != second.digest
    assert first.digest != changed_runbook.digest


def test_recovery_drill_cannot_claim_pass_outside_objective() -> None:
    objective = RecoveryObjective(max_recovery_seconds=30, max_data_loss_units=0)
    assert RecoveryDrill("d1", "c1", 30, 0, True).verify(objective)
    assert not RecoveryDrill("d2", "c1", 31, 0, False).verify(objective)

    with pytest.raises(ValueError, match="pass claim"):
        RecoveryDrill("d3", "c1", 31, 0, True).verify(objective)
    with pytest.raises(ValueError, match="pass claim"):
        RecoveryDrill("d4", "c1", 10, 0, False).verify(objective)


def test_recovery_objective_rejects_boolean_and_negative_limits() -> None:
    with pytest.raises(ValueError):
        RecoveryObjective(max_recovery_seconds=-1, max_data_loss_units=0)
    with pytest.raises(ValueError):
        RecoveryObjective(max_recovery_seconds=True, max_data_loss_units=0)
