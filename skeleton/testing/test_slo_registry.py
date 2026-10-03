from __future__ import annotations

import pytest

from skeleton.ai.runtime.observability.slo import (
    SLI,
    SLO,
    SLOAssessment,
    SLOError,
    SLOWindow,
    ServiceLevelObjective,
    SLOTracker,
    assess_slo,
)


def _window() -> SLOWindow:
    return SLOWindow(
        window_id="window-1",
        start_ns=100,
        end_ns=1_000,
        excluded_conditions=("maintenance", "synthetic-probe"),
    )


def _slo(target: float = 0.99) -> SLO:
    return SLO(
        slo_id="assistant.availability",
        service_id="assistant",
        sli_name="successful_requests",
        target=target,
        window=_window(),
    )


def test_typed_slo_preserves_existing_tracker_surface() -> None:
    tracker = SLOTracker()
    legacy = ServiceLevelObjective(name="legacy.availability", target=0.99)
    tracker.register(legacy)
    tracker.record("legacy.availability", bad=False)

    assert tracker.remaining("legacy.availability") >= 0.0
    assert "legacy.availability" in tracker.status()


def test_slo_window_canonicalizes_declared_exclusions() -> None:
    window = SLOWindow(
        window_id="window-1",
        start_ns=100,
        end_ns=1_000,
        excluded_conditions=("synthetic-probe", "maintenance", "maintenance"),
    )

    assert window.excluded_conditions == ("maintenance", "synthetic-probe")
    assert len(window.digest) == 64


def test_sli_value_uses_only_eligible_events() -> None:
    sli = SLI(
        observation_id="obs-1",
        slo_id="assistant.availability",
        good_events=98,
        total_events=100,
        excluded_events=1,
        observed_start_ns=100,
        observed_end_ns=900,
    )

    assert sli.eligible_events == 99
    assert sli.value == pytest.approx(98 / 99)


def test_slo_assessment_binds_exact_slo_and_sli() -> None:
    slo = _slo(target=0.98)
    sli = SLI(
        observation_id="obs-1",
        slo_id=slo.slo_id,
        good_events=98,
        total_events=100,
        excluded_events=0,
        observed_start_ns=100,
        observed_end_ns=900,
    )

    assessment = assess_slo(slo=slo, sli=sli)

    assert assessment.met is True
    assert assessment.value == pytest.approx(0.98)
    assert assessment.slo_digest == slo.digest
    assert assessment.sli_digest == sli.digest
    assert len(assessment.digest) == 64


def test_slo_assessment_reports_miss_without_granting_authority() -> None:
    slo = _slo(target=0.999)
    sli = SLI(
        observation_id="obs-miss",
        slo_id=slo.slo_id,
        good_events=990,
        total_events=1_000,
        observed_start_ns=100,
        observed_end_ns=900,
    )

    assessment = assess_slo(slo=slo, sli=sli)

    assert assessment.met is False
    assert not hasattr(assessment, "release_allowed")
    assert not hasattr(assessment, "override")


def test_sli_must_belong_to_same_slo() -> None:
    with pytest.raises(SLOError, match="different SLO"):
        assess_slo(
            slo=_slo(),
            sli=SLI(
                observation_id="obs-other",
                slo_id="other.slo",
                good_events=10,
                total_events=10,
                observed_start_ns=100,
                observed_end_ns=900,
            ),
        )


@pytest.mark.parametrize(
    ("start", "end"),
    (
        (99, 900),
        (100, 1_001),
    ),
)
def test_sli_must_be_contained_in_declared_window(
    start: int,
    end: int,
) -> None:
    slo = _slo()
    sli = SLI(
        observation_id="obs-outside",
        slo_id=slo.slo_id,
        good_events=10,
        total_events=10,
        observed_start_ns=start,
        observed_end_ns=end,
    )

    with pytest.raises(SLOError, match="contained in declared SLO window"):
        assess_slo(slo=slo, sli=sli)


def test_sli_rejects_impossible_counts() -> None:
    with pytest.raises(SLOError, match="excluded_events cannot exceed"):
        SLI(
            observation_id="obs-bad-excluded",
            slo_id="assistant.availability",
            good_events=0,
            total_events=10,
            excluded_events=11,
            observed_start_ns=100,
            observed_end_ns=900,
        )

    with pytest.raises(SLOError, match="good_events cannot exceed eligible"):
        SLI(
            observation_id="obs-bad-good",
            slo_id="assistant.availability",
            good_events=10,
            total_events=10,
            excluded_events=1,
            observed_start_ns=100,
            observed_end_ns=900,
        )


def test_empty_eligible_population_is_not_divide_by_zero() -> None:
    sli = SLI(
        observation_id="obs-all-excluded",
        slo_id="assistant.availability",
        good_events=0,
        total_events=5,
        excluded_events=5,
        observed_start_ns=100,
        observed_end_ns=900,
    )

    assert sli.eligible_events == 0
    assert sli.value == 1.0


def test_slo_rejects_invalid_target_and_window() -> None:
    with pytest.raises(SLOError, match=r"within \[0, 1\]"):
        _slo(target=1.1)

    with pytest.raises(SLOError, match="end must be after start"):
        SLOWindow(
            window_id="bad-window",
            start_ns=100,
            end_ns=100,
        )


def test_assessment_rejects_forged_digest_or_value() -> None:
    with pytest.raises(SLOError, match="sha256"):
        SLOAssessment(
            slo_digest="bad",
            sli_digest="b" * 64,
            value=0.99,
            met=True,
        )

    with pytest.raises(SLOError, match=r"within \[0, 1\]"):
        SLOAssessment(
            slo_digest="a" * 64,
            sli_digest="b" * 64,
            value=1.2,
            met=True,
        )
