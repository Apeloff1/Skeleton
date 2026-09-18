from __future__ import annotations

import pytest

from skeleton.jeeves.agent.lens_hypergraph import HyperedgeKind, HypergraphPolicy, SemanticLensHypergraph
from skeleton.jeeves.agent.semantic_lenses import LensFamily, ReadingStatus, SemanticFinding
from skeleton.jeeves.agent.semantic_maximal import MaximalSemanticRuntime


def _finding(
    finding_id: str,
    lens: str,
    family: LensFamily,
    *,
    confidence: float = 0.82,
    ambiguity: float = 0.25,
    counterreading: str = "",
) -> SemanticFinding:
    return SemanticFinding(
        finding_id=finding_id,
        lens_key=lens,
        family=family,
        observation_ids=("obs-1", "obs-2"),
        interpretation=f"Reading from {lens}",
        prediction=f"{lens} predicts a discriminating future observation.",
        confidence=confidence,
        ambiguity=ambiguity,
        novelty=0.7,
        status=ReadingStatus.CONTESTED if counterreading else ReadingStatus.CANDIDATE,
        evidence_ids=("ev-1",),
        counterreading=counterreading,
    )


def test_three_way_hyperedge_preserves_family_diversity_and_confidence_cap() -> None:
    findings = (
        _finding("film", "rashomon_variance", LensFamily.FILM),
        _finding("game", "information_set", LensFamily.GAME),
        _finding("memory", "source_monitoring", LensFamily.COGNITIVE),
    )
    graph = SemanticLensHypergraph(policy=HypergraphPolicy(max_order=4, confidence_cap=0.70))
    snapshot = graph.build(findings, calibration_weights={f.lens_key: 0.6 for f in findings})
    three_way = [edge for edge in snapshot.edges if len(edge.finding_ids) == 3]
    assert three_way
    edge = three_way[0]
    assert len(edge.families) == 3
    assert edge.confidence <= 0.70 + 1e-12
    assert edge.metadata["interpretive_only"] is True
    assert edge.metadata["may_promote_to_evidence"] is False
    assert edge.evidence_ids == ("ev-1",)


def test_counterreading_creates_unresolved_contradiction_hyperedge() -> None:
    findings = (
        _finding("a", "rashomon_variance", LensFamily.FILM),
        _finding(
            "b",
            "source_monitoring",
            LensFamily.COGNITIVE,
            counterreading="The disagreement is strategic rather than mnemonic.",
        ),
    )
    snapshot = SemanticLensHypergraph().build(findings)
    assert snapshot.unresolved_edge_ids
    unresolved = [edge for edge in snapshot.edges if edge.unresolved]
    assert unresolved
    assert all(edge.kind is HyperedgeKind.CONTRADICTION for edge in unresolved)
    assert all(edge.ambiguity >= 0.60 for edge in unresolved)


def test_perpendicular_restart_expands_into_missing_families() -> None:
    findings = (
        _finding("film", "rashomon_variance", LensFamily.FILM),
        _finding("game", "information_set", LensFamily.GAME),
        _finding("memory", "source_monitoring", LensFamily.COGNITIVE),
    )
    snapshot = SemanticLensHypergraph().build(findings)
    assert LensFamily.FILM in snapshot.restart.represented_families
    assert LensFamily.LITERATURE in snapshot.restart.missing_families
    assert snapshot.restart.tangent_seeds
    assert any(seed.lens_key == "perpendicular:literature" for seed in snapshot.restart.tangent_seeds)


def test_maximal_runtime_persists_perpendicular_seeds_in_existing_tangent_graph() -> None:
    findings = (
        _finding("film", "rashomon_variance", LensFamily.FILM),
        _finding("game", "information_set", LensFamily.GAME),
        _finding("memory", "source_monitoring", LensFamily.COGNITIVE),
    )
    runtime = MaximalSemanticRuntime()
    result = runtime.compose(findings, sequence=7, frontier_limit=10)
    assert result.tangent_ids
    assert result.frontier.tangent_ids
    assert set(result.frontier.tangent_ids) <= {node.tangent_id for node in runtime.graph.snapshot()}
    weights = dict(result.scientific_weights)
    assert weights["information_set"] == pytest.approx(0.10)
    assert weights["rashomon_variance"] == pytest.approx(0.10)
    assert weights["source_monitoring"] == pytest.approx(0.10)
    checkpoint = runtime.graph.checkpoint(
        root_fingerprint=result.hypergraph.restart.parent_fingerprint,
        sequence=8,
    )
    assert checkpoint.open_ids
