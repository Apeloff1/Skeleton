from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.assignment_balance import (
    BalanceAssignment,
    analyze_assignment_balance,
)
from skeleton.ai.research.model_internals.reverse_engineering.causal_invariance import (
    EnvironmentEffect,
    analyze_causal_invariance,
)
from skeleton.ai.research.model_internals.reverse_engineering.intervention_transfer import (
    TransferObservation,
    analyze_intervention_transfer,
)
from skeleton.ai.research.model_internals.reverse_engineering.multiple_testing import (
    HypothesisPValue,
    benjamini_hochberg,
)
from skeleton.ai.research.model_internals.reverse_engineering.probe_frontier import (
    FrontierProbe,
    analyze_probe_frontier,
)
from skeleton.ai.research.model_internals.reverse_engineering.provenance_graph import (
    ProvenanceNode,
    verify_provenance_graph,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_causal_invariance_accepts_consistent_environment_effects():
    probe = d("probe")
    report = analyze_causal_invariance(
        (
            EnvironmentEffect("a", probe, "e1", 0.9),
            EnvironmentEffect("b", probe, "e2", 0.8),
            EnvironmentEffect("c", probe, "e3", 0.85),
        ),
        max_deviation_tolerance=0.1,
    )
    assert report.invariant is True
    assert report.sign_consistency == 1.0


def test_intervention_transfer_tracks_cross_model_sign_agreement():
    intervention = d("intervention")
    observations = (
        TransferObservation("a", intervention, "m1", d("s1"), 0.5),
        TransferObservation("b", intervention, "m2", d("s1"), 0.4),
        TransferObservation("c", intervention, "m1", d("s2"), 0.3),
        TransferObservation("d", intervention, "m2", d("s2"), 0.2),
    )
    report = analyze_intervention_transfer(observations)
    assert report.transferable is True
    assert report.sign_agreement_ratio == 1.0


def test_provenance_graph_verifies_dag_and_depth():
    report = verify_provenance_graph(
        (
            ProvenanceNode("r", "report", d("r")),
            ProvenanceNode("c", "claim", d("c"), ("r",)),
            ProvenanceNode("x", "replication", d("x"), ("c",)),
        )
    )
    assert report.cycle_free is True
    assert report.missing_parent_count == 0
    assert report.max_depth == 2
    assert report.root_count == 1
    assert report.leaf_count == 1


def test_assignment_balance_detects_within_one_balance():
    report = analyze_assignment_balance(
        (
            BalanceAssignment("u1", "a", "s1"),
            BalanceAssignment("u2", "b", "s1"),
            BalanceAssignment("u3", "a", "s1"),
            BalanceAssignment("u4", "a", "s2"),
            BalanceAssignment("u5", "b", "s2"),
        )
    )
    assert report.all_strata_within_one is True
    assert report.maximum_stratum_arm_count_difference == 1


def test_probe_frontier_removes_dominated_probe():
    report = analyze_probe_frontier(
        (
            FrontierProbe("a", 1.0, 10.0, 0.1),
            FrontierProbe("b", 2.0, 9.0, 0.2),
            FrontierProbe("c", 0.5, 8.0, 0.05),
        )
    )
    assert "b" in report.dominated_ids
    assert "a" in report.frontier_ids


def test_benjamini_hochberg_controls_false_discovery_rate():
    report = benjamini_hochberg(
        (
            HypothesisPValue("h1", 0.001),
            HypothesisPValue("h2", 0.01),
            HypothesisPValue("h3", 0.2),
            HypothesisPValue("h4", 0.8),
        ),
        alpha=0.05,
    )
    rejected = {item.hypothesis_id for item in report.adjusted if item.rejected}
    assert rejected == {"h1", "h2"}
