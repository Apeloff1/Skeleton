from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.adaptive_design import (
    AdaptiveExperimentCandidate,
    select_adaptive_experiments,
)
from skeleton.ai.research.model_internals.reverse_engineering.hierarchical_uncertainty import (
    HierarchicalObservation,
    analyze_hierarchical_uncertainty,
)
from skeleton.ai.research.model_internals.reverse_engineering.nonlinear_mediation import (
    NonlinearMediationObservation,
    analyze_nonlinear_mediation,
)
from skeleton.ai.research.model_internals.reverse_engineering.replication_meta import (
    ReplicationStudy,
    analyze_replication_meta,
)
from skeleton.ai.research.model_internals.reverse_engineering.stopping_rule import (
    StoppingEvidence,
    evaluate_stopping_rule,
)
from skeleton.ai.research.model_internals.reverse_engineering.transportability import (
    TransportObservation,
    analyze_transportability,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_adaptive_design_prioritizes_high_information_per_cost():
    decision = select_adaptive_experiments(
        (
            AdaptiveExperimentCandidate("a", "causal", 1.0, 10.0, 2.0),
            AdaptiveExperimentCandidate("b", "artifact", 0.5, 2.0, 1.0),
            AdaptiveExperimentCandidate("c", "causal", 1.0, 8.0, 3.0, prerequisite_ids=("a",)),
        ),
        budget=5.0,
    )
    assert decision.selected_ids == ("a", "c")
    assert decision.total_cost == 5.0


def test_hierarchical_uncertainty_reports_between_group_structure():
    report = analyze_hierarchical_uncertainty(
        (
            HierarchicalObservation("a", "g1", 0.0),
            HierarchicalObservation("b", "g1", 0.1),
            HierarchicalObservation("c", "g2", 1.0),
            HierarchicalObservation("d", "g2", 1.1),
        )
    )
    assert report.group_count == 2
    assert report.between_group_variance > report.within_group_variance
    assert report.intraclass_correlation is not None
    assert report.intraclass_correlation > 0.9


def test_nonlinear_mediation_tracks_dose_specific_mediated_effect():
    probe = d("probe")
    observations = []
    for dose, treated, blocked in (
        (0.0, 1.0, 0.8),
        (1.0, 2.0, 1.2),
    ):
        observations.extend(
            (
                NonlinearMediationObservation(f"c-{dose}", probe, dose, False, False, 0.0),
                NonlinearMediationObservation(f"t-{dose}", probe, dose, True, False, treated),
                NonlinearMediationObservation(f"b-{dose}", probe, dose, True, True, blocked),
            )
        )
    report = analyze_nonlinear_mediation(tuple(observations))
    assert report.dose_count == 2
    assert report.peak_mediated_dose == 1.0
    assert report.peak_absolute_mediated_effect == 0.8


def test_transportability_accepts_small_preserved_effect_gap():
    probe = d("probe")
    report = analyze_transportability(
        (
            TransportObservation("a", probe, "source-a", "source", 0.8),
            TransportObservation("b", probe, "source-b", "source", 0.9),
            TransportObservation("c", probe, "target-a", "target", 0.75),
            TransportObservation("d", probe, "target-b", "target", 0.8),
        ),
        absolute_gap_tolerance=0.1,
    )
    assert report.sign_preserved is True
    assert report.transportable is True


def test_stopping_rule_stops_supported_precise_replicated_effect():
    decision = evaluate_stopping_rule(
        StoppingEvidence(
            sample_count=100,
            confidence_interval_width=0.05,
            effect_magnitude=0.8,
            minimum_effect_of_interest=0.5,
            replication_ratio=0.9,
            contradiction_weight=0.05,
        )
    )
    assert decision.action == "stop_supported"
    assert decision.should_stop is True


def test_replication_meta_pools_independent_effects():
    claim = d("claim")
    report = analyze_replication_meta(
        (
            ReplicationStudy("a", claim, 0.8, 0.1, "lab-a"),
            ReplicationStudy("b", claim, 1.0, 0.1, "lab-b"),
            ReplicationStudy("c", claim, 0.9, 0.2, "lab-c"),
        )
    )
    assert report.independent_actor_count == 3
    assert 0.8 < report.pooled_effect < 1.0
    assert report.sign_agreement_ratio == 1.0
