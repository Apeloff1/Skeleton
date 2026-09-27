from __future__ import annotations

import pytest

from skeleton.release.slo_promotion import (
    CanarySLOSignal,
    OperatorOverride,
    ReleaseAction,
    ReleasePromotionError,
    ReleaseSLOPolicy,
    ReleaseSLOPromotionController,
)


def _signal(
    *,
    stage: int,
    observed_at: int = 100,
    samples: int = 300,
    error_rate: float = 0.002,
    latency: float = 220.0,
    quality: float = 0.99,
) -> CanarySLOSignal:
    return CanarySLOSignal(
        release_id="release-42",
        service="engine",
        from_version="v41",
        to_version="v42",
        stage_percent=stage,
        samples=samples,
        error_rate=error_rate,
        p99_latency_ms=latency,
        provider_quality=quality,
        observed_at=observed_at,
    )


def test_healthy_observability_promotes_with_order_stable_receipt() -> None:
    controller = ReleaseSLOPromotionController(
        ReleaseSLOPolicy(min_samples=500)
    )
    early = _signal(stage=10, observed_at=100)
    late = _signal(stage=50, observed_at=110)

    first = controller.evaluate(
        [late, early],
        evaluated_at=120,
    )
    second = controller.evaluate(
        [early, late],
        evaluated_at=120,
    )

    assert first.action is ReleaseAction.PROMOTE
    assert first.reasons == ()
    assert first.signal_digests == second.signal_digests
    assert first.digest == second.digest


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"error_rate": 0.02}, "error_rate_exceeded"),
        ({"latency": 1500.0}, "latency_exceeded"),
        ({"quality": 0.80}, "provider_quality_below_threshold"),
    ],
)
def test_unhealthy_canary_automatically_rolls_back(kwargs, reason) -> None:
    controller = ReleaseSLOPromotionController()
    receipt = controller.evaluate(
        [_signal(stage=10, samples=600, **kwargs)],
        evaluated_at=120,
    )

    assert receipt.action is ReleaseAction.ROLLBACK
    assert reason in receipt.reasons


def test_insufficient_samples_holds_without_promoting_or_rolling_back() -> None:
    controller = ReleaseSLOPromotionController(
        ReleaseSLOPolicy(min_samples=1000)
    )
    receipt = controller.evaluate(
        [_signal(stage=10, samples=500)],
        evaluated_at=120,
    )

    assert receipt.action is ReleaseAction.HOLD
    assert receipt.reasons == ("insufficient_samples",)


def test_operator_can_conservatively_override_healthy_release() -> None:
    controller = ReleaseSLOPromotionController()
    override = OperatorOverride(
        operator_id="operator-a",
        requested_action=ReleaseAction.ROLLBACK,
        reason="incident correlation requires rollback",
        issued_at=115,
        incident_ref="incident-42",
    )

    receipt = controller.evaluate(
        [_signal(stage=25, samples=600)],
        evaluated_at=120,
        override=override,
    )

    assert receipt.action is ReleaseAction.ROLLBACK
    assert receipt.override_digest == override.digest
    assert "operator_override:incident-42" in receipt.reasons


def test_operator_cannot_promote_over_failed_slo_evidence() -> None:
    controller = ReleaseSLOPromotionController()
    override = OperatorOverride(
        operator_id="operator-a",
        requested_action=ReleaseAction.PROMOTE,
        reason="force it",
        issued_at=115,
        incident_ref="incident-unsafe",
    )

    with pytest.raises(
        ReleasePromotionError,
        match="cannot promote failed SLO evidence",
    ):
        controller.evaluate(
            [_signal(stage=25, samples=600, error_rate=0.5)],
            evaluated_at=120,
            override=override,
        )


def test_stale_observability_fails_to_automatic_rollback() -> None:
    controller = ReleaseSLOPromotionController(
        ReleaseSLOPolicy(max_signal_age_seconds=10)
    )

    receipt = controller.evaluate(
        [_signal(stage=10, observed_at=100, samples=600)],
        evaluated_at=200,
    )

    assert receipt.action is ReleaseAction.ROLLBACK
    assert "stale_or_future_signal" in receipt.reasons


def test_signal_source_must_be_observability() -> None:
    with pytest.raises(
        ReleasePromotionError,
        match="must come from observability",
    ):
        CanarySLOSignal(
            release_id="release-42",
            service="engine",
            from_version="v41",
            to_version="v42",
            stage_percent=10,
            samples=600,
            error_rate=0.0,
            p99_latency_ms=100.0,
            provider_quality=1.0,
            observed_at=100,
            source="self-reported",
        )
