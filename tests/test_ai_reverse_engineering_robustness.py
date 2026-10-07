from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.adversarial_probe import (
    AdversarialProbePair,
    analyze_adversarial_probe_robustness,
)
from skeleton.ai.research.model_internals.reverse_engineering.circuit_motifs import (
    DirectedCircuitEdge,
    analyze_circuit_motifs,
)
from skeleton.ai.research.model_internals.reverse_engineering.feature_interaction import (
    FeatureInteractionObservation,
    analyze_feature_interactions,
)
from skeleton.ai.research.model_internals.reverse_engineering.long_context_interference import (
    InterferenceTrial,
    analyze_long_context_interference,
)
from skeleton.ai.research.model_internals.reverse_engineering.memory_decay import (
    MemoryDecayTrial,
    analyze_memory_decay,
)
from skeleton.ai.research.model_internals.reverse_engineering.tool_policy_boundary import (
    ToolPolicyTrial,
    analyze_tool_policy_boundary,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_adversarial_probe_reports_degradation():
    probe = d("probe")
    report = analyze_adversarial_probe_robustness(
        (
            AdversarialProbePair("a", probe, 1.0, 0.8, d("b1"), d("a1")),
            AdversarialProbePair("b", probe, 0.9, 0.6, d("b2"), d("a2")),
        )
    )
    assert abs(report.mean_score_drop - 0.25) < 1e-12
    assert report.output_change_ratio == 1.0
    assert report.worst_score_drop > 0.29


def test_long_context_interference_finds_threshold_crossing():
    probe = d("probe")
    report = analyze_long_context_interference(
        (
            InterferenceTrial("a", probe, 0, 100, 1.0, d("a")),
            InterferenceTrial("b", probe, 1000, 100, 0.9, d("b")),
            InterferenceTrial("c", probe, 5000, 100, 0.7, d("c")),
        )
    )
    assert report.first_below_threshold_units == 5000
    assert abs(report.fidelity_drop - 0.3) < 1e-12
    assert report.monotonicity_violations == 0


def test_memory_decay_finds_half_recall_horizon():
    memory = d("memory")
    report = analyze_memory_decay(
        (
            MemoryDecayTrial("a", memory, 0, 1.0),
            MemoryDecayTrial("b", memory, 10, 0.8),
            MemoryDecayTrial("c", memory, 20, 0.5),
            MemoryDecayTrial("d", memory, 40, 0.2),
        )
    )
    assert report.half_recall_delay == 20
    assert report.recall_drop == 0.8


def test_tool_policy_boundary_catches_unauthorized_execution():
    report = analyze_tool_policy_boundary(
        (
            ToolPolicyTrial("a", d("a"), "read", True, True, True),
            ToolPolicyTrial("b", d("b"), "write", False, False, False),
            ToolPolicyTrial("c", d("c"), "admin", False, True, True),
        )
    )
    assert report.unauthorized_execution_count == 1
    assert report.allow_accuracy == 1.0
    assert report.deny_accuracy == 0.5


def test_feature_interaction_reports_positive_synergy():
    probe = d("probe")
    report = analyze_feature_interactions(
        (
            FeatureInteractionObservation("a", probe, "f1", "f2", 0.0, 0.2, 0.3, 0.8),
            FeatureInteractionObservation("b", probe, "f1", "f2", 0.0, 0.1, 0.4, 0.7),
        )
    )[0]
    assert report.mean_synergy > 0.2
    assert report.positive_synergy_ratio == 1.0
    assert report.sign_consistency == 1.0


def test_circuit_motifs_count_chain_and_fanout():
    report = analyze_circuit_motifs(
        (
            DirectedCircuitEdge("a", "b"),
            DirectedCircuitEdge("b", "c"),
            DirectedCircuitEdge("b", "d"),
            DirectedCircuitEdge("x", "b"),
        )
    )
    assert report.chain_count == 4
    assert report.fan_in_node_count == 1
    assert report.fan_out_node_count == 1
    assert report.source_count == 2
    assert report.sink_count == 2
