from __future__ import annotations

import pytest

from skeleton.ai.runtime.observability.profile_records import (
    PerformanceFinding,
    ProfileRecordError,
    ProfileRun,
    ProfileSample,
    compare_profiles,
)


def _run(
    run_id: str,
    durations: tuple[float, ...],
    *,
    workload: str = "assistant-chat",
    environment: str = "linux-x86_64",
    operation: str = "model.invoke",
    phase: str = "steady_state",
) -> ProfileRun:
    return ProfileRun(
        run_id=run_id,
        workload_id=workload,
        environment_id=environment,
        operation_id=operation,
        phase=phase,
        samples=tuple(
            ProfileSample(
                operation_id=operation,
                phase=phase,
                duration_ms=value,
                sample_index=index + 1,
            )
            for index, value in enumerate(durations)
        ),
    )


def test_profile_run_retains_workload_environment_and_phase_identity() -> None:
    run = _run("run-1", (10.0, 20.0, 30.0))

    assert run.workload_id == "assistant-chat"
    assert run.environment_id == "linux-x86_64"
    assert run.operation_id == "model.invoke"
    assert run.phase == "steady_state"
    assert run.mean_ms == pytest.approx(20.0)
    assert len(run.digest) == 64


def test_profile_run_sorts_samples_by_index_deterministically() -> None:
    run = ProfileRun(
        run_id="run-order",
        workload_id="assistant-chat",
        environment_id="linux-x86_64",
        operation_id="model.invoke",
        phase="steady_state",
        samples=(
            ProfileSample("model.invoke", "steady_state", 30.0, 3),
            ProfileSample("model.invoke", "steady_state", 10.0, 1),
            ProfileSample("model.invoke", "steady_state", 20.0, 2),
        ),
    )

    assert tuple(sample.sample_index for sample in run.samples) == (1, 2, 3)
    assert run.durations_ms == (10.0, 20.0, 30.0)


def test_profile_comparison_detects_mean_regression() -> None:
    baseline = _run("baseline", (10.0, 10.0, 10.0))
    candidate = _run("candidate", (12.0, 12.0, 12.0))

    finding = compare_profiles(
        baseline=baseline,
        candidate=candidate,
        metric="mean_ms",
    )

    assert finding.regressed is True
    assert finding.regression_ppm == 200_000
    assert finding.baseline_value_ms == pytest.approx(10.0)
    assert finding.candidate_value_ms == pytest.approx(12.0)
    assert len(finding.digest) == 64


def test_profile_comparison_detects_improvement_without_regression_flag() -> None:
    finding = compare_profiles(
        baseline=_run("baseline", (20.0, 20.0)),
        candidate=_run("candidate", (10.0, 10.0)),
        metric="mean_ms",
    )

    assert finding.regressed is False
    assert finding.regression_ppm == -500_000


@pytest.mark.parametrize(
    ("field", "candidate_kwargs"),
    (
        ("workload", {"workload": "other-workload"}),
        ("environment", {"environment": "arm64-linux"}),
        ("operation", {"operation": "tool.invoke"}),
        ("phase", {"phase": "tail"}),
    ),
)
def test_profile_comparison_rejects_identity_mismatch(
    field: str,
    candidate_kwargs: dict[str, str],
) -> None:
    del field
    baseline = _run("baseline", (10.0, 11.0))
    candidate = _run("candidate", (10.0, 11.0), **candidate_kwargs)

    with pytest.raises(
        ProfileRecordError,
        match="identical workload/environment/operation/phase identity",
    ):
        compare_profiles(
            baseline=baseline,
            candidate=candidate,
            metric="mean_ms",
        )


def test_profile_run_rejects_sample_operation_mismatch() -> None:
    with pytest.raises(
        ProfileRecordError,
        match="sample operation identity mismatch",
    ):
        ProfileRun(
            run_id="run-bad-operation",
            workload_id="assistant-chat",
            environment_id="linux-x86_64",
            operation_id="model.invoke",
            phase="steady_state",
            samples=(
                ProfileSample("tool.invoke", "steady_state", 10.0, 1),
            ),
        )


def test_profile_run_rejects_sample_phase_mismatch() -> None:
    with pytest.raises(
        ProfileRecordError,
        match="sample phase mismatch",
    ):
        ProfileRun(
            run_id="run-bad-phase",
            workload_id="assistant-chat",
            environment_id="linux-x86_64",
            operation_id="model.invoke",
            phase="steady_state",
            samples=(
                ProfileSample("model.invoke", "tail", 10.0, 1),
            ),
        )


def test_profile_run_rejects_duplicate_sample_indexes() -> None:
    with pytest.raises(
        ProfileRecordError,
        match="sample indexes must be unique",
    ):
        ProfileRun(
            run_id="run-duplicate-index",
            workload_id="assistant-chat",
            environment_id="linux-x86_64",
            operation_id="model.invoke",
            phase="steady_state",
            samples=(
                ProfileSample("model.invoke", "steady_state", 10.0, 1),
                ProfileSample("model.invoke", "steady_state", 11.0, 1),
            ),
        )


@pytest.mark.parametrize("phase", ("startup", "steady_state", "tail"))
def test_profile_phases_are_explicit(phase: str) -> None:
    run = _run("run-phase", (10.0,), phase=phase)

    assert run.phase == phase


def test_unknown_profile_phase_is_rejected() -> None:
    with pytest.raises(
        ProfileRecordError,
        match="phase must be startup, steady_state, or tail",
    ):
        ProfileSample(
            operation_id="model.invoke",
            phase="mixed",
            duration_ms=10.0,
            sample_index=1,
        )


def test_nonfinite_or_negative_duration_is_rejected() -> None:
    with pytest.raises(
        ProfileRecordError,
        match="finite and non-negative",
    ):
        ProfileSample(
            operation_id="model.invoke",
            phase="steady_state",
            duration_ms=float("nan"),
            sample_index=1,
        )

    with pytest.raises(
        ProfileRecordError,
        match="finite and non-negative",
    ):
        ProfileSample(
            operation_id="model.invoke",
            phase="steady_state",
            duration_ms=-1.0,
            sample_index=1,
        )


def test_profile_comparison_rejects_unknown_metric() -> None:
    with pytest.raises(
        ProfileRecordError,
        match="mean_ms, p95_ms, or p99_ms",
    ):
        compare_profiles(
            baseline=_run("baseline", (10.0,)),
            candidate=_run("candidate", (10.0,)),
            metric="max_ms",
        )


def test_zero_baseline_nonzero_candidate_is_explicit_large_regression() -> None:
    finding = compare_profiles(
        baseline=_run("baseline", (0.0,)),
        candidate=_run("candidate", (1.0,)),
        metric="mean_ms",
    )

    assert finding.regressed is True
    assert finding.regression_ppm == 1_000_000_000


def test_performance_finding_rejects_forged_regression_summary() -> None:
    with pytest.raises(
        ProfileRecordError,
        match="must match baseline/candidate measurements",
    ):
        PerformanceFinding(
            baseline_run_digest="a" * 64,
            candidate_run_digest="b" * 64,
            metric="mean_ms",
            baseline_value_ms=10.0,
            candidate_value_ms=12.0,
            regression_ppm=100_000,
            regressed=True,
        )
