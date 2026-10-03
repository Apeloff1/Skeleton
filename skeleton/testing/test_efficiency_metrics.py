from __future__ import annotations

import pytest

from skeleton.ai.runtime.observability.efficiency_metrics import (
    ComputeObservation,
    EfficiencyMetricError,
    compare_efficiency,
    metric_for,
)


def _obs(
    observation_id: str,
    *,
    hardware: str,
    compute_seconds: float,
    energy_joules: float,
    quality: str = "a",
    reliability: str = "b",
    workload: str = "assistant-benchmark",
    protocol: str = "bench-v1",
    work_units: float = 100.0,
) -> ComputeObservation:
    return ComputeObservation(
        observation_id=observation_id,
        workload_id=workload,
        protocol_id=protocol,
        hardware_id=hardware,
        work_units=work_units,
        compute_seconds=compute_seconds,
        energy_joules=energy_joules,
        quality_digest=quality * 64,
        reliability_digest=reliability * 64,
    )


def test_efficiency_metric_is_normalized_by_work_units() -> None:
    observation = _obs(
        "baseline",
        hardware="cpu-a",
        compute_seconds=50.0,
        energy_joules=1_000.0,
    )
    metric = metric_for(observation)

    assert metric.compute_seconds_per_unit == pytest.approx(0.5)
    assert metric.energy_joules_per_unit == pytest.approx(10.0)
    assert metric.observation_digest == observation.digest
    assert len(metric.digest) == 64


def test_efficiency_claim_allows_hardware_change_with_equivalent_evidence() -> None:
    baseline = _obs(
        "baseline",
        hardware="cpu-a",
        compute_seconds=50.0,
        energy_joules=1_000.0,
    )
    candidate = _obs(
        "candidate",
        hardware="cpu-b",
        compute_seconds=40.0,
        energy_joules=800.0,
    )

    claim = compare_efficiency(
        baseline=baseline,
        candidate=candidate,
    )

    assert claim.compute_improvement_ppm == 200_000
    assert claim.energy_improvement_ppm == 200_000
    assert claim.quality_equivalent is True
    assert claim.reliability_equivalent is True
    assert claim.valid is True
    assert len(claim.digest) == 64


def test_quality_change_invalidates_efficiency_claim() -> None:
    claim = compare_efficiency(
        baseline=_obs(
            "baseline",
            hardware="cpu-a",
            compute_seconds=50.0,
            energy_joules=1_000.0,
        ),
        candidate=_obs(
            "candidate",
            hardware="cpu-b",
            compute_seconds=40.0,
            energy_joules=800.0,
            quality="c",
        ),
    )

    assert claim.compute_improvement_ppm > 0
    assert claim.quality_equivalent is False
    assert claim.valid is False


def test_reliability_change_invalidates_efficiency_claim() -> None:
    claim = compare_efficiency(
        baseline=_obs(
            "baseline",
            hardware="cpu-a",
            compute_seconds=50.0,
            energy_joules=1_000.0,
        ),
        candidate=_obs(
            "candidate",
            hardware="cpu-b",
            compute_seconds=40.0,
            energy_joules=800.0,
            reliability="d",
        ),
    )

    assert claim.reliability_equivalent is False
    assert claim.valid is False


def test_no_improvement_is_not_a_valid_efficiency_claim() -> None:
    claim = compare_efficiency(
        baseline=_obs(
            "baseline",
            hardware="cpu-a",
            compute_seconds=50.0,
            energy_joules=1_000.0,
        ),
        candidate=_obs(
            "candidate",
            hardware="cpu-b",
            compute_seconds=55.0,
            energy_joules=1_100.0,
        ),
    )

    assert claim.compute_improvement_ppm < 0
    assert claim.energy_improvement_ppm < 0
    assert claim.valid is False


@pytest.mark.parametrize(
    ("field", "candidate_kwargs", "message"),
    (
        (
            "workload",
            {"workload": "different-workload"},
            "identical workload",
        ),
        (
            "protocol",
            {"protocol": "bench-v2"},
            "identical benchmark protocol",
        ),
        (
            "work_units",
            {"work_units": 50.0},
            "identical work-unit count",
        ),
    ),
)
def test_efficiency_comparison_rejects_incomparable_measurements(
    field: str,
    candidate_kwargs: dict[str, object],
    message: str,
) -> None:
    del field
    baseline = _obs(
        "baseline",
        hardware="cpu-a",
        compute_seconds=50.0,
        energy_joules=1_000.0,
    )
    candidate = _obs(
        "candidate",
        hardware="cpu-b",
        compute_seconds=40.0,
        energy_joules=800.0,
        **candidate_kwargs,
    )

    with pytest.raises(EfficiencyMetricError, match=message):
        compare_efficiency(
            baseline=baseline,
            candidate=candidate,
        )


def test_efficiency_observation_rejects_nonfinite_or_zero_measurements() -> None:
    with pytest.raises(
        EfficiencyMetricError,
        match="finite and positive",
    ):
        _obs(
            "bad",
            hardware="cpu-a",
            compute_seconds=float("nan"),
            energy_joules=1_000.0,
        )

    with pytest.raises(
        EfficiencyMetricError,
        match="finite and positive",
    ):
        _obs(
            "bad-zero",
            hardware="cpu-a",
            compute_seconds=50.0,
            energy_joules=0.0,
        )


def test_efficiency_observation_rejects_invalid_evidence_digest() -> None:
    with pytest.raises(
        EfficiencyMetricError,
        match="lowercase sha256",
    ):
        ComputeObservation(
            observation_id="bad-digest",
            workload_id="assistant-benchmark",
            protocol_id="bench-v1",
            hardware_id="cpu-a",
            work_units=100.0,
            compute_seconds=50.0,
            energy_joules=1_000.0,
            quality_digest="not-a-digest",
            reliability_digest="b" * 64,
        )
