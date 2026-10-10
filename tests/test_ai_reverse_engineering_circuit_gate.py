from __future__ import annotations

from hashlib import sha256

from skeleton.ai.research.model_internals.reverse_engineering.circuit_graph import (
    CircuitEdgeObservation,
    build_circuit_graph,
)
from skeleton.ai.research.model_internals.reverse_engineering.claim_gate import (
    ClaimQualityEvidence,
    evaluate_claim_quality,
)


def d(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def test_circuit_graph_aggregates_reproduced_edges():
    probe = d("probe")
    report = build_circuit_graph(
        (
            CircuitEdgeObservation("a", probe, "l1:u2", "l4:u7", 0.8, True),
            CircuitEdgeObservation("b", probe, "l1:u2", "l4:u7", 1.0, True),
            CircuitEdgeObservation("c", probe, "l2:u3", "l4:u7", 0.2, False),
        )
    )
    assert report.node_count == 3
    assert report.edge_count == 2
    assert report.strongest_edge == ("l1:u2", "l4:u7")
    strongest = next(edge for edge in report.edges if edge.source_node == "l1:u2")
    assert strongest.mean_effect == 0.9
    assert strongest.sign_consistency == 1.0
    assert strongest.reproduction_ratio == 1.0


def test_claim_gate_passes_only_complete_high_quality_evidence():
    decision = evaluate_claim_quality(
        ClaimQualityEvidence(
            claim_id="family:gqa",
            evidence_digest=d("evidence"),
            balanced_accuracy=0.9,
            attribution_stability=0.8,
            standardized_effect=1.2,
            independent_domains=4,
            replication_ratio=0.9,
            contradiction_weight=0.1,
        )
    )
    assert decision.status == "pass"
    assert decision.promotable is True
    assert decision.failed_checks == ()


def test_claim_gate_holds_missing_replication_and_rejects_heavy_contradiction():
    held = evaluate_claim_quality(
        ClaimQualityEvidence(
            claim_id="family:mqa",
            evidence_digest=d("held"),
            balanced_accuracy=0.9,
            attribution_stability=0.8,
            standardized_effect=1.2,
            independent_domains=3,
            replication_ratio=None,
            contradiction_weight=0.1,
        )
    )
    assert held.status == "hold"
    assert "replication" in held.failed_checks

    rejected = evaluate_claim_quality(
        ClaimQualityEvidence(
            claim_id="family:moe",
            evidence_digest=d("rejected"),
            balanced_accuracy=0.95,
            attribution_stability=0.9,
            standardized_effect=2.0,
            independent_domains=5,
            replication_ratio=1.0,
            contradiction_weight=0.8,
        )
    )
    assert rejected.status == "reject"
    assert "contradiction" in rejected.failed_checks
