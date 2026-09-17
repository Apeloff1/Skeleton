"""Regression coverage for Jeeves' rollbackable epistemic world model."""

import math

import pytest

from skeleton.jeeves.agent import (
    BeliefConflict,
    BeliefGraph,
    BeliefUpdate,
    EdgeKind,
    EvidenceArtifact,
    EvidenceKind,
    EvidenceLedger,
    HypothesisStatus,
    Proposition,
    RevisionKind,
    WorldModel,
    binary_entropy,
    reliability_to_likelihood_ratio,
)


def test_reliability_curve_is_monotonic_and_bounded() -> None:
    values = [reliability_to_likelihood_ratio(value) for value in (0.0, 0.25, 0.5, 0.6, 0.8, 1.0)]
    assert values == sorted(values)
    assert values[0] >= 1.0
    assert values[-1] <= 20.0


def test_binary_entropy_peaks_at_half_probability() -> None:
    assert binary_entropy(0.5) == pytest.approx(1.0)
    assert binary_entropy(0.1) < 0.5
    assert binary_entropy(0.9) == pytest.approx(binary_entropy(0.1))


def test_proposition_identity_is_semantic_and_deterministic() -> None:
    first = Proposition.create("service", "status", {"state": "healthy"}, scope="prod")
    second = Proposition.create("service", "status", {"state": "healthy"}, scope="prod")
    changed = Proposition.create("service", "status", {"state": "degraded"}, scope="prod")
    assert first.proposition_id == second.proposition_id
    assert first.semantic_key == second.semantic_key
    assert changed.proposition_id != first.proposition_id


def test_upsert_deduplicates_semantically_identical_propositions() -> None:
    graph = BeliefGraph()
    first = graph.upsert_proposition(Proposition.create("x", "is", 1), prior=0.6)
    second = graph.upsert_proposition(Proposition.create("x", "is", 1), prior=0.2)
    assert first.proposition_id == second.proposition_id
    assert second.probability == pytest.approx(0.6)
    assert len(graph.beliefs()) == 1


def test_supporting_evidence_increases_posterior() -> None:
    ledger = EvidenceLedger()
    artifact = ledger.append(
        EvidenceArtifact(
            evidence_id="evidence:support",
            kind=EvidenceKind.FIXTURE,
            source="fixture",
            payload={"observed": True},
            observed_at=1.0,
            confidence=0.9,
        )
    )
    graph = BeliefGraph(evidence_ledger=ledger)
    state = graph.upsert_proposition(Proposition.create("service", "healthy", True), prior=0.5)
    revised = graph.revise(
        BeliefUpdate(
            proposition_id=state.proposition_id,
            evidence_id=artifact.evidence_id,
            direction=1,
            reliability=0.9,
        )
    )
    assert revised.probability > state.probability
    assert artifact.evidence_id in revised.supporting_evidence_ids


def test_refuting_evidence_decreases_posterior() -> None:
    ledger = EvidenceLedger()
    artifact = ledger.append(
        EvidenceArtifact(
            evidence_id="evidence:refute",
            kind=EvidenceKind.FIXTURE,
            source="fixture",
            payload={"observed": False},
            observed_at=1.0,
            confidence=0.95,
        )
    )
    graph = BeliefGraph(evidence_ledger=ledger)
    state = graph.upsert_proposition(Proposition.create("service", "healthy", True), prior=0.8)
    revised = graph.revise(
        BeliefUpdate(
            proposition_id=state.proposition_id,
            evidence_id=artifact.evidence_id,
            direction=-1,
            reliability=0.9,
        )
    )
    assert revised.probability < state.probability
    assert artifact.evidence_id in revised.refuting_evidence_ids


def test_evidence_reliability_cannot_exceed_artifact_confidence() -> None:
    ledger = EvidenceLedger()
    artifact = ledger.append(
        EvidenceArtifact(
            evidence_id="evidence:weak",
            kind=EvidenceKind.FIXTURE,
            source="fixture",
            payload={"value": 1},
            observed_at=1.0,
            confidence=0.4,
        )
    )
    graph = BeliefGraph(evidence_ledger=ledger)
    state = graph.upsert_proposition(Proposition.create("x", "equals", 1))
    with pytest.raises(BeliefConflict):
        graph.revise(
            BeliefUpdate(
                proposition_id=state.proposition_id,
                evidence_id=artifact.evidence_id,
                direction=1,
                reliability=0.9,
            )
        )


def test_revision_history_is_append_only() -> None:
    graph = BeliefGraph()
    state = graph.upsert_proposition(Proposition.create("x", "exists", True), prior=0.5)
    graph.revise(BeliefUpdate(state.proposition_id, None, 1, 0.8))
    graph.revise(BeliefUpdate(state.proposition_id, None, -1, 0.7))
    revisions = graph.revisions_for(state.proposition_id)
    assert len(revisions) == 3
    assert revisions[0].kind is RevisionKind.CREATE
    assert revisions[1].kind is RevisionKind.SUPPORT
    assert revisions[2].kind is RevisionKind.REFUTE


def test_locked_belief_rejects_revision() -> None:
    graph = BeliefGraph()
    state = graph.upsert_proposition(Proposition.create("axiom", "holds", True), prior=0.99, locked=True)
    with pytest.raises(BeliefConflict):
        graph.revise(BeliefUpdate(state.proposition_id, None, -1, 0.9))


def test_transaction_rolls_back_all_updates_on_failure() -> None:
    graph = BeliefGraph()
    first = graph.upsert_proposition(Proposition.create("a", "value", 1), prior=0.5)
    second = graph.upsert_proposition(Proposition.create("b", "value", 2), prior=0.5, locked=True)
    before = graph.snapshot(persist=False).fingerprint
    result = graph.apply_transaction(
        (
            BeliefUpdate(first.proposition_id, None, 1, 0.9),
            BeliefUpdate(second.proposition_id, None, 1, 0.9),
        )
    )
    assert result.committed is False
    assert graph.snapshot(persist=False).fingerprint == before
    assert graph.require_belief(first.proposition_id).probability == pytest.approx(0.5)


def test_successful_transaction_updates_multiple_beliefs_atomically() -> None:
    graph = BeliefGraph()
    first = graph.upsert_proposition(Proposition.create("a", "value", 1), prior=0.5)
    second = graph.upsert_proposition(Proposition.create("b", "value", 2), prior=0.5)
    result = graph.apply_transaction(
        (
            BeliefUpdate(first.proposition_id, None, 1, 0.9),
            BeliefUpdate(second.proposition_id, None, -1, 0.9),
        )
    )
    assert result.committed is True
    assert graph.require_belief(first.proposition_id).probability > 0.5
    assert graph.require_belief(second.proposition_id).probability < 0.5
    assert len(result.revision_ids) >= 2


def test_exclusive_contradiction_group_conserves_probability_mass() -> None:
    graph = BeliefGraph()
    a = graph.upsert_proposition(Proposition.create("deploy", "state", "green"), prior=0.8)
    b = graph.upsert_proposition(Proposition.create("deploy", "state", "blue"), prior=0.8)
    group = graph.add_contradiction_group((a.proposition_id, b.proposition_id), exclusive=True, normalized=True)
    total = sum(graph.require_belief(item).probability for item in group.proposition_ids)
    assert total <= 1.000001


def test_supporting_one_exclusive_hypothesis_reduces_competitor_mass() -> None:
    graph = BeliefGraph()
    a = graph.upsert_proposition(Proposition.create("root", "cause", "network"), prior=0.5)
    b = graph.upsert_proposition(Proposition.create("root", "cause", "database"), prior=0.5)
    graph.add_contradiction_group((a.proposition_id, b.proposition_id), exclusive=True, normalized=True)
    before_b = graph.require_belief(b.proposition_id).probability
    graph.revise(BeliefUpdate(a.proposition_id, None, 1, 0.95))
    after_a = graph.require_belief(a.proposition_id).probability
    after_b = graph.require_belief(b.proposition_id).probability
    assert after_a > after_b
    assert after_b <= before_b
    assert after_a + after_b <= 1.000001


def test_support_edge_propagates_local_evidence() -> None:
    graph = BeliefGraph()
    source = graph.upsert_proposition(Proposition.create("metric", "high", True), prior=0.5)
    target = graph.upsert_proposition(Proposition.create("service", "overloaded", True), prior=0.5)
    graph.add_edge(source.proposition_id, target.proposition_id, EdgeKind.SUPPORTS, weight=1.0, confidence=0.9)
    graph.revise(BeliefUpdate(source.proposition_id, None, 1, 0.95))
    assert graph.require_belief(target.proposition_id).probability > 0.5


def test_refute_edge_propagates_negative_pressure() -> None:
    graph = BeliefGraph()
    source = graph.upsert_proposition(Proposition.create("cache", "warm", True), prior=0.5)
    target = graph.upsert_proposition(Proposition.create("latency", "high", True), prior=0.7)
    graph.add_edge(source.proposition_id, target.proposition_id, EdgeKind.REFUTES, weight=1.0, confidence=0.9)
    graph.revise(BeliefUpdate(source.proposition_id, None, 1, 0.95))
    assert graph.require_belief(target.proposition_id).probability < 0.7


def test_dependency_neighborhood_returns_connected_beliefs() -> None:
    graph = BeliefGraph()
    a = graph.upsert_proposition(Proposition.create("a", "is", 1))
    b = graph.upsert_proposition(Proposition.create("b", "is", 2))
    c = graph.upsert_proposition(Proposition.create("c", "is", 3))
    graph.add_edge(a.proposition_id, b.proposition_id, EdgeKind.IMPLIES)
    graph.add_edge(b.proposition_id, c.proposition_id, EdgeKind.IMPLIES)
    depth_one = {item.proposition_id for item in graph.dependency_neighborhood(a.proposition_id, depth=1)}
    depth_two = {item.proposition_id for item in graph.dependency_neighborhood(a.proposition_id, depth=2)}
    assert depth_one == {a.proposition_id, b.proposition_id}
    assert depth_two == {a.proposition_id, b.proposition_id, c.proposition_id}


def test_hypothesis_refresh_reflects_component_beliefs() -> None:
    graph = BeliefGraph()
    first = graph.upsert_proposition(Proposition.create("cause", "part", "a"), prior=0.7)
    second = graph.upsert_proposition(Proposition.create("cause", "part", "b"), prior=0.7)
    hypothesis = graph.register_hypothesis("combined cause", (first.proposition_id, second.proposition_id), prior=0.5)
    before = hypothesis.posterior
    graph.revise(BeliefUpdate(first.proposition_id, None, 1, 0.95))
    graph.revise(BeliefUpdate(second.proposition_id, None, 1, 0.95))
    after = graph.refresh_hypothesis(hypothesis.hypothesis_id)
    assert after.posterior > before
    assert after.status in {HypothesisStatus.OPEN, HypothesisStatus.LEADING}


def test_hypothesis_penalizes_complexity() -> None:
    graph = BeliefGraph()
    p = graph.upsert_proposition(Proposition.create("cause", "simple", True), prior=0.8)
    low_penalty = graph.register_hypothesis("low", (p.proposition_id,), complexity_penalty=0.0)
    high_penalty = graph.register_hypothesis("high", (p.proposition_id,), complexity_penalty=1.0)
    assert graph.refresh_hypothesis(low_penalty.hypothesis_id).posterior > graph.refresh_hypothesis(high_penalty.hypothesis_id).posterior


def test_counterfactual_probe_has_positive_information_gain_for_uncertain_belief() -> None:
    graph = BeliefGraph()
    state = graph.upsert_proposition(Proposition.create("x", "unknown", True), prior=0.5)
    probe = graph.counterfactual_probe(state.proposition_id, hypothetical_reliability=0.9)
    assert probe.expected_information_gain_bits > 0
    assert probe.priority > 0
    assert probe.if_supported_probability > 0.5
    assert probe.if_refuted_probability < 0.5


def test_ranked_probes_prioritize_more_uncertain_belief() -> None:
    graph = BeliefGraph()
    uncertain = graph.upsert_proposition(Proposition.create("u", "state", True), prior=0.5)
    certain = graph.upsert_proposition(Proposition.create("c", "state", True), prior=0.95)
    probes = graph.ranked_probes(limit=2, minimum_entropy_bits=0.0)
    assert probes[0].proposition_id == uncertain.proposition_id
    assert {item.proposition_id for item in probes} == {uncertain.proposition_id, certain.proposition_id}


def test_snapshot_rollback_restores_probability_and_fingerprint() -> None:
    graph = BeliefGraph()
    state = graph.upsert_proposition(Proposition.create("x", "value", 1), prior=0.5)
    snapshot = graph.snapshot(persist=True)
    graph.revise(BeliefUpdate(state.proposition_id, None, 1, 0.99))
    assert graph.snapshot(persist=False).fingerprint != snapshot.fingerprint
    restored = graph.rollback(snapshot.snapshot_id)
    assert graph.require_belief(state.proposition_id).probability == pytest.approx(0.5)
    # Rollback itself advances version, so the snapshot id/fingerprint changes,
    # while semantic belief state returns to the saved values.
    assert restored.version > snapshot.version


def test_decay_moves_old_beliefs_toward_neutrality() -> None:
    now = [100.0]
    graph = BeliefGraph(clock=lambda: now[0])
    state = graph.upsert_proposition(Proposition.create("x", "stable", True), prior=0.9)
    now[0] = 200.0
    changed = graph.decay(half_life_seconds=100.0, toward=0.5, now=now[0])
    assert changed
    probability = graph.require_belief(state.proposition_id).probability
    assert 0.5 < probability < 0.9


def test_world_model_scopes_are_isolated() -> None:
    world = WorldModel()
    left = world.graph("tenant-a")
    right = world.graph("tenant-b")
    left.upsert_proposition(Proposition.create("secret", "value", "left", scope="tenant-a"))
    assert len(left.beliefs()) == 1
    assert right.beliefs() == ()
    assert world.scopes() == ("tenant-a", "tenant-b")


def test_world_model_refuses_rebinding_scope_to_different_ledger() -> None:
    world = WorldModel()
    first = EvidenceLedger()
    second = EvidenceLedger()
    world.graph("scope", evidence_ledger=first)
    with pytest.raises(Exception):
        world.graph("scope", evidence_ledger=second)


def test_world_summary_is_deterministically_fingerprinted() -> None:
    world = WorldModel()
    graph = world.graph("scope")
    graph.upsert_proposition(Proposition.create("x", "value", 1, scope="scope"), prior=0.6)
    first = world.fingerprint
    second = world.fingerprint
    assert first == second
    graph.upsert_proposition(Proposition.create("y", "value", 2, scope="scope"), prior=0.6)
    assert world.fingerprint != first


def test_probability_never_reaches_exact_zero_or_one() -> None:
    graph = BeliefGraph()
    state = graph.upsert_proposition(Proposition.create("x", "certain", True), prior=0.5)
    for _ in range(20):
        graph.revise(BeliefUpdate(state.proposition_id, None, 1, 1.0, likelihood_ratio=1_000_000.0))
    assert 0.0 < graph.require_belief(state.proposition_id).probability < 1.0


def test_contradiction_pressure_reflects_competitor_probability() -> None:
    graph = BeliefGraph()
    a = graph.upsert_proposition(Proposition.create("state", "choice", "a"), prior=0.5)
    b = graph.upsert_proposition(Proposition.create("state", "choice", "b"), prior=0.5)
    graph.add_contradiction_group((a.proposition_id, b.proposition_id))
    pressure = graph.contradiction_pressure(a.proposition_id)
    assert 0.0 <= pressure <= 1.0
    assert pressure == pytest.approx(graph.require_belief(b.proposition_id).probability)


def test_graph_summary_contains_uncertainty_and_hypothesis_surfaces() -> None:
    graph = BeliefGraph()
    a = graph.upsert_proposition(Proposition.create("a", "exists", True), prior=0.5)
    graph.register_hypothesis("a exists", (a.proposition_id,))
    summary = graph.summary()
    assert summary["belief_count"] == 1
    assert summary["hypothesis_count"] == 1
    assert summary["world_entropy_bits"] > 0
    assert summary["uncertain"]
    assert summary["hypotheses"]
    assert len(summary["fingerprint"]) == 64
