from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.reliability_release import (
    CanaryController,
    CanaryObservation,
    DeploymentSafety,
    FeatureFlag,
    FeatureFlagAuthority,
    RollbackPlan,
)


def _canary() -> CanaryController:
    return CanaryController(
        min_samples=10,
        max_error_rate=0.05,
        min_quality=0.9,
        max_latency_ratio=1.2,
    )


def _good() -> CanaryObservation:
    return CanaryObservation(10, 0.01, 0.95, 1.0)


def _rollback(**overrides: object) -> RollbackPlan:
    values = {
        "release_id": "r1",
        "reversible": True,
        "data_compatible": True,
        "external_effects_reconciled": True,
        "steps": ("stop rollout", "restore artifact", "verify state"),
    }
    values.update(overrides)
    return RollbackPlan(**values)


def test_promotion_requires_safe_rollback_preflight() -> None:
    promoted = DeploymentSafety.decide(
        release_id="r1",
        canary=_canary(),
        observation=_good(),
        rollback=_rollback(),
        now=1,
    )
    assert promoted.canary_decision == "promote"
    assert promoted.decision == "promote"
    assert len(promoted.digest) == 64

    for field in ("reversible", "data_compatible", "external_effects_reconciled"):
        held = DeploymentSafety.decide(
            release_id="r1",
            canary=_canary(),
            observation=_good(),
            rollback=_rollback(**{field: False}),
            now=1,
        )
        assert held.decision == "hold"


def test_canary_rollback_dominates_other_conditions() -> None:
    receipt = DeploymentSafety.decide(
        release_id="r1",
        canary=_canary(),
        observation=CanaryObservation(10, 0.2, 0.95, 1.0),
        rollback=_rollback(reversible=False),
        now=1,
    )
    assert receipt.canary_decision == "rollback"
    assert receipt.decision == "rollback"


def test_feature_flag_requires_explicit_scoped_authority() -> None:
    flag = FeatureFlag("new-router", True, 100)
    with pytest.raises(PermissionError, match="explicit authority"):
        DeploymentSafety.decide(
            release_id="r1",
            canary=_canary(),
            observation=_good(),
            rollback=_rollback(),
            now=1,
            flag=flag,
        )

    with pytest.raises(PermissionError, match="outside principal"):
        DeploymentSafety.decide(
            release_id="r1",
            canary=_canary(),
            observation=_good(),
            rollback=_rollback(),
            now=1,
            flag=flag,
            flag_authority=FeatureFlagAuthority("worker", ("other",)),
        )


def test_security_sensitive_flag_enable_is_fail_closed() -> None:
    flag = FeatureFlag("bypass", True, 100, security_sensitive=True)
    weak = FeatureFlagAuthority("worker", ("bypass",))
    with pytest.raises(PermissionError, match="security-sensitive"):
        DeploymentSafety.decide(
            release_id="r1",
            canary=_canary(),
            observation=_good(),
            rollback=_rollback(),
            now=1,
            flag=flag,
            flag_authority=weak,
        )

    strong = FeatureFlagAuthority("release-authority", ("bypass",), True)
    assert DeploymentSafety.decide(
        release_id="r1",
        canary=_canary(),
        observation=_good(),
        rollback=_rollback(),
        now=1,
        flag=flag,
        flag_authority=strong,
    ).decision == "promote"


def test_expired_enabled_flag_holds_promotion() -> None:
    flag = FeatureFlag("new-router", True, 10)
    receipt = DeploymentSafety.decide(
        release_id="r1",
        canary=_canary(),
        observation=_good(),
        rollback=_rollback(),
        now=10,
        flag=flag,
        flag_authority=FeatureFlagAuthority("worker", ("new-router",)),
    )
    assert not receipt.flag_effective
    assert receipt.decision == "hold"


def test_rollback_plan_is_evidence_bound_and_validated() -> None:
    first = _rollback()
    changed = _rollback(steps=("stop rollout", "restore artifact", "verify state", "reconcile"))
    assert first.digest != changed.digest

    with pytest.raises(TypeError):
        _rollback(reversible=1)
    with pytest.raises(ValueError, match="unique"):
        _rollback(steps=("restore", "restore"))


def test_release_identity_must_match_rollback_plan() -> None:
    with pytest.raises(ValueError, match="release mismatch"):
        DeploymentSafety.decide(
            release_id="r2",
            canary=_canary(),
            observation=_good(),
            rollback=_rollback(),
            now=1,
        )
