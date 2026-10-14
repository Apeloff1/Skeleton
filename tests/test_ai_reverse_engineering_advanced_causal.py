from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.circuit_centrality import (
    WeightedCircuitEdge,
    analyze_circuit_centrality,
)
from skeleton.ai.research.model_internals.reverse_engineering.contradiction_matrix import (
    PropositionEvidence,
    build_contradiction_matrix,
)
from skeleton.ai.research.model_internals.reverse_engineering.cross_seed_stability import (
    SeedMeasurement,
    analyze_cross_seed_stability,
)
from skeleton.ai.research.model_internals.reverse_engineering.evidence_quorum import (
    DomainEvidence,
    evaluate_evidence_quorum,
)
from skeleton.ai.research.model_internals.reverse_engineering.negative_control import (
    NegativeControlObservation,
    analyze_negative_controls,
)
from skeleton.ai.research.model_internals.reverse_engineering.path_patching import (
    PathPatchObservation,
    analyze_path_patching,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_path_patching_recovers_mediator_effect():
    probe = d("probe")
    report = analyze_path_patching(
        (
            PathPatchObservation("a", probe, "s", "m", "t", 1.0, 0.0, 0.8),
            PathPatchObservation("b", probe, "s", "m", "t", 1.0, 0.0, 0.6),
        )
    )[0]
    assert report.mean_recoverable_effect == 1.0
    assert abs(report.mean_recovered_effect - 0.7) < 1e-12
    assert abs(report.mean_recovery_fraction - 0.7) < 1e-12
    assert report.positive_recovery_ratio == 1.0


def test_negative_controls_flag_leakage():
    report = analyze_negative_controls(
        (
            NegativeControlObservation("a", "shuffle", 0.0, 0.01, 0.05),
            NegativeControlObservation("b", "shuffle", 0.0, 0.02, 0.05),
            NegativeControlObservation("c", "random", 0.0, 0.5, 0.05),
        ),
        minimum_pass_ratio=0.8,
    )
    assert report.leak_suspected is True
    assert report.failing_count == 1


def test_cross_seed_stability_reports_tight_metrics():
    probe = d("probe")
    report = analyze_cross_seed_stability(
        (
            SeedMeasurement("a", probe, 1, 0.90),
            SeedMeasurement("b", probe, 2, 0.92),
            SeedMeasurement("c", probe, 3, 0.88),
        ),
        tolerance=0.03,
    )
    assert report.metric_range < 0.05
    assert report.within_tolerance_ratio == 1.0


def test_contradiction_matrix_surfaces_mutual_conflict():
    report = build_contradiction_matrix(
        (
            PropositionEvidence("a", d("a"), (), ("b",)),
            PropositionEvidence("b", d("b"), (), ("a",)),
            PropositionEvidence("c", d("c"), (), ()),
        )
    )
    assert report.contradiction_pair_count == 1
    assert report.mutual_pair_count == 1
    assert report.isolated_proposition_count == 1


def test_circuit_centrality_finds_highest_weight_node():
    report = analyze_circuit_centrality(
        (
            WeightedCircuitEdge("a", "b", 1.0),
            WeightedCircuitEdge("b", "c", 2.0),
            WeightedCircuitEdge("b", "d", 3.0),
        )
    )
    assert report.highest_total_weight_node == "b"
    assert report.highest_total_weight == 6.0


def test_evidence_quorum_requires_independent_domains():
    evidence = (
        DomainEvidence("a", "attention", d("a"), 0.95, True),
        DomainEvidence("b", "kv", d("b"), 0.90, True),
        DomainEvidence("c", "artifact", d("c"), 0.85, True),
        DomainEvidence("d", "routing", d("d"), 0.10, False),
    )
    report = evaluate_evidence_quorum(evidence)
    assert report.supporting_domain_count == 3
    assert report.quorum_met is True
