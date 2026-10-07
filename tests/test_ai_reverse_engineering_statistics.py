from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.bootstrap_ci import (
    BootstrapConfig,
    bootstrap_mean_interval,
)
from skeleton.ai.research.model_internals.reverse_engineering.calibration_drift import (
    CalibrationWindow,
    analyze_calibration_drift,
)
from skeleton.ai.research.model_internals.reverse_engineering.mediation import (
    MediationObservation,
    analyze_mediation,
)
from skeleton.ai.research.model_internals.reverse_engineering.permutation_null import (
    permutation_mean_difference,
)
from skeleton.ai.research.model_internals.reverse_engineering.rank_sensitivity import (
    RankedFeatureList,
    analyze_rank_sensitivity,
)
from skeleton.ai.research.model_internals.reverse_engineering.sequential_evidence import (
    SequentialObservation,
    analyze_sequential_evidence,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_bootstrap_interval_is_deterministic_and_contains_mean():
    config = BootstrapConfig(resamples=500, confidence=0.9, seed=17)
    first = bootstrap_mean_interval((1.0, 2.0, 3.0, 4.0), config=config)
    second = bootstrap_mean_interval((1.0, 2.0, 3.0, 4.0), config=config)
    assert first.digest == second.digest
    assert first.lower <= first.mean <= first.upper
    assert first.mean == 2.5


def test_permutation_null_detects_large_group_shift():
    report = permutation_mean_difference(
        (0.0, 0.1, 0.2, 0.3),
        (3.0, 3.1, 3.2, 3.3),
        permutations=1000,
        seed=3,
    )
    assert report.observed_difference > 2.9
    assert report.two_sided_p_value < 0.05


def test_sequential_evidence_crosses_support_boundary():
    observations = tuple(
        SequentialObservation(str(index), True)
        for index in range(12)
    )
    report = analyze_sequential_evidence(observations, accept_log_likelihood=2.0)
    assert report.decision == "support"
    assert report.boundary_crossing_index is not None
    assert report.success_rate == 1.0


def test_calibration_drift_flags_large_balanced_accuracy_change():
    report = analyze_calibration_drift(
        (
            CalibrationWindow("a", 0, 0.95, 0.95, 0.9),
            CalibrationWindow("b", 1, 0.90, 0.90, 0.85),
            CalibrationWindow("c", 2, 0.60, 0.70, 0.65),
        ),
        threshold=0.1,
    )
    assert report.drift_exceeds_threshold is True
    assert report.max_adjacent_balanced_accuracy_change > 0.2


def test_mediation_separates_direct_and_mediated_effect():
    probe = d("probe")
    observations = (
        MediationObservation("c1", probe, False, False, 0.0),
        MediationObservation("c2", probe, False, False, 0.0),
        MediationObservation("t1", probe, True, False, 1.0),
        MediationObservation("t2", probe, True, False, 1.0),
        MediationObservation("b1", probe, True, True, 0.25),
        MediationObservation("b2", probe, True, True, 0.25),
    )
    report = analyze_mediation(observations)
    assert report.total_effect == 1.0
    assert report.direct_effect == 0.25
    assert report.mediated_effect == 0.75
    assert report.mediated_fraction == 0.75


def test_rank_sensitivity_reports_stable_prefix():
    probe = d("probe")
    report = analyze_rank_sensitivity(
        (
            RankedFeatureList("a", probe, ("f1", "f2", "f3", "f4")),
            RankedFeatureList("b", probe, ("f1", "f2", "x3", "x4")),
            RankedFeatureList("c", probe, ("f1", "f2", "y3", "y4")),
        ),
        stable_threshold=0.5,
    )
    assert report.stable_prefix_length >= 2
    assert report.points[0].mean_pairwise_jaccard == 1.0
