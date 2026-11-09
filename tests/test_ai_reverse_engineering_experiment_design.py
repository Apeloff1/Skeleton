from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.circuit_discovery import (
    CandidateEdge,
    discover_circuit_candidates,
)
from skeleton.ai.research.model_internals.reverse_engineering.experimental_power import (
    plan_two_group_power,
)
from skeleton.ai.research.model_internals.reverse_engineering.intervention_equivalence import (
    InterventionEffectPair,
    analyze_intervention_equivalence,
)
from skeleton.ai.research.model_internals.reverse_engineering.mediation_graph import (
    MediationEdge,
    analyze_mediation_graph,
)
from skeleton.ai.research.model_internals.reverse_engineering.probe_scheduler import (
    ProbeTask,
    schedule_probes,
)
from skeleton.ai.research.model_internals.reverse_engineering.randomized_assignment import (
    AssignmentUnit,
    build_balanced_assignment,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_power_plan_increases_for_smaller_effect():
    large = plan_two_group_power(1.0)
    small = plan_two_group_power(0.5)
    assert small.samples_per_group > large.samples_per_group
    assert large.total_samples == large.samples_per_group * 2


def test_stratified_assignment_balances_arms():
    units = tuple(
        AssignmentUnit(f"u{i}", "a" if i < 6 else "b")
        for i in range(12)
    )
    plan = build_balanced_assignment(units, ("control", "treatment"), seed=7)
    counts = {stratum: dict(values) for stratum, values in plan.per_stratum_counts}
    assert counts["a"]["control"] == 3
    assert counts["a"]["treatment"] == 3
    assert counts["b"]["control"] == 3
    assert counts["b"]["treatment"] == 3


def test_mediation_graph_multiplies_path_coefficients():
    report = analyze_mediation_graph(
        (
            MediationEdge("s", "m1", 0.5),
            MediationEdge("m1", "t", 0.8),
            MediationEdge("s", "m2", 0.2),
            MediationEdge("m2", "t", 0.5),
        ),
        source="s",
        target="t",
    )
    effects = sorted(path.path_effect for path in report.paths)
    assert effects == [0.1, 0.4]
    assert abs(report.total_indirect_effect - 0.5) < 1e-12


def test_intervention_equivalence_uses_matched_effect_tolerance():
    report = analyze_intervention_equivalence(
        (
            InterventionEffectPair("a", d("a"), "patch", "ablate", 0.8, 0.82),
            InterventionEffectPair("b", d("b"), "patch", "ablate", 0.6, 0.58),
            InterventionEffectPair("c", d("c"), "patch", "ablate", 0.7, 0.72),
        ),
        tolerance=0.05,
    )
    assert report.equivalent is True
    assert report.within_tolerance_ratio == 1.0


def test_circuit_discovery_filters_weak_unreplicated_edges():
    report = discover_circuit_candidates(
        (
            CandidateEdge("s", "a", 0.9, 1.0, 1.0),
            CandidateEdge("a", "t", 0.8, 0.9, 1.0),
            CandidateEdge("s", "b", 0.05, 1.0, 1.0),
            CandidateEdge("b", "t", 0.9, 0.5, 1.0),
        ),
        source="s",
        target="t",
    )
    assert report.retained_edge_count == 2
    assert report.candidate_count == 1
    assert report.candidates[0].nodes == ("s", "a", "t")


def test_probe_scheduler_honors_budget_and_prerequisites():
    schedule = schedule_probes(
        (
            ProbeTask("base", "behavior", 2.0, 4.0),
            ProbeTask("causal", "causal", 3.0, 9.0, prerequisite_ids=("base",)),
            ProbeTask("expensive", "artifact", 10.0, 100.0),
        ),
        budget=5.0,
    )
    assert schedule.selected_ids == ("base", "causal")
    assert schedule.spent == 5.0
    assert "expensive" in schedule.skipped_ids
