from __future__ import annotations

import pytest

from skeleton.jeeves.agent.associative_memory import (
    AssociationKind,
    AssociativeMemoryGameIndex,
    AssociativeMemoryMesh,
)
from skeleton.jeeves.agent.memory import MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGamePolicy


class FakeClock:
    def __init__(self, value: float = 1_000_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _namespace(user: str = "user") -> MemoryNamespace:
    return MemoryNamespace("tenant", user, "workspace", "session")


def _index(clock: FakeClock) -> AssociativeMemoryGameIndex:
    return AssociativeMemoryGameIndex(
        policy=MemoryGamePolicy(minimum_score=0.0),
        clock=clock,
    )


def test_sequence_capture_builds_relations_without_pretending_retrieval_was_tested() -> None:
    clock = FakeClock()
    index = _index(clock)
    namespace = _namespace()
    cards = index.capture_sequence(
        namespace,
        (
            "User opens the deployment panel.",
            "User checks deterministic replay evidence.",
            "User reviews rollback status.",
        ),
        context_tags=("release",),
    )
    assert len(cards) == 3
    neighbors = index.mesh.neighbors(
        namespace,
        cards[0].card_id,
        kinds=(AssociationKind.TEMPORAL_FORWARD,),
    )
    assert len(neighbors) == 1
    edge = neighbors[0].association
    assert edge.target_card_id == cards[1].card_id
    assert edge.observations == 1
    assert edge.tested_retrievals == 0
    assert edge.successes == 0
    assert edge.retrieval_success_probability == pytest.approx(0.5)


def test_successful_retrieval_updates_tested_count_not_historical_truth() -> None:
    clock = FakeClock()
    index = _index(clock)
    namespace = _namespace()
    cards = index.capture_sequence(namespace, ("alpha cue", "beta target"))
    before = index.mesh.neighbors(namespace, cards[0].card_id, kinds=(AssociationKind.TEMPORAL_FORWARD,))[0]
    assert before.association.tested_retrievals == 0
    updated = index.mesh.record_retrieval_outcome(
        namespace,
        cards[0].card_id,
        cards[1].card_id,
        success=True,
    )
    assert len(updated) == 1
    after = updated[0]
    assert after.tested_retrievals == 1
    assert after.successes == 1
    assert after.observations == 2
    assert after.retrieval_success_probability > 0.5
    assert after.posterior_strength > before.posterior_strength


def test_failed_retrieval_is_distinct_from_unobserved_test() -> None:
    clock = FakeClock()
    mesh = AssociativeMemoryMesh(clock=clock)
    namespace = _namespace()
    edge = mesh.observe(
        namespace,
        "source",
        "target",
        kind=AssociationKind.TASK_SEQUENCE,
        strength=0.7,
        success=None,
    )
    assert edge.tested_retrievals == 0
    failed = mesh.observe(
        namespace,
        "source",
        "target",
        kind=AssociationKind.TASK_SEQUENCE,
        strength=0.7,
        success=False,
    )
    assert failed.tested_retrievals == 1
    assert failed.successes == 0
    assert failed.retrieval_success_probability < 0.5


def test_sequence_prediction_learns_short_context_and_backoff() -> None:
    clock = FakeClock()
    index = _index(clock)
    namespace = _namespace()
    cards = index.capture_sequence(namespace, ("open repo", "inspect tests", "run validation"))
    prediction = index.mesh.predict_next(namespace, [cards[0].card_id, cards[1].card_id])
    assert prediction.candidates
    assert prediction.candidates[0][0] == cards[2].card_id
    assert prediction.candidates[0][1] == pytest.approx(1.0)
    assert prediction.evidence_count >= 1
    assert prediction.entropy_bits == pytest.approx(0.0)


def test_associative_search_can_surface_related_card_without_mutating_trust() -> None:
    clock = FakeClock()
    index = _index(clock)
    namespace = _namespace()
    cards = index.capture_sequence(
        namespace,
        (
            "compiler semantic provenance",
            "decompiler reversible reconstruction",
        ),
        trust=0.77,
        salience=0.8,
    )
    target_trust_before = cards[1].trust
    hits = index.search(namespace, "compiler semantic provenance", limit=10)
    ids = {hit.card.card_id for hit in hits}
    assert cards[0].card_id in ids
    assert cards[1].card_id in ids
    stored_target = index.store.get(cards[1].card_id)
    assert stored_target is not None
    assert stored_target.trust == pytest.approx(target_trust_before)


def test_juxtaposition_strengthens_relation_but_is_not_a_retrieval_success() -> None:
    clock = FakeClock()
    index = _index(clock)
    namespace = _namespace()
    left = index.capture_interaction(namespace, "Neutral face after a bowl of soup.")
    right = index.capture_interaction(namespace, "The same neutral face after a coffin.")
    forward, reverse = index.mesh.observe_juxtaposition(
        namespace,
        left.card_id,
        right.card_id,
        changed_interpretation=True,
        evidence_ids=("paired-context-study",),
    )
    assert forward.kind is AssociationKind.JUXTAPOSITION
    assert reverse.kind is AssociationKind.JUXTAPOSITION
    assert forward.strength == pytest.approx(0.8)
    assert forward.tested_retrievals == 0
    assert forward.successes == 0
    assert forward.metadata["interpretation_changed"] is True
    assert forward.metadata["retrieval_test"] is False


def test_association_graph_is_namespace_isolated() -> None:
    clock = FakeClock()
    index = _index(clock)
    alice = _namespace("alice")
    bob = _namespace("bob")
    alice_cards = index.capture_sequence(alice, ("private alpha", "private beta"))
    bob_cards = index.capture_sequence(bob, ("public gamma", "public delta"))
    alice_neighbors = index.mesh.neighbors(alice, alice_cards[0].card_id)
    assert alice_neighbors
    assert all(hit.association.namespace.user_id == "alice" for hit in alice_neighbors)
    assert index.mesh.neighbors(bob, alice_cards[0].card_id) == ()
    bob_prediction = index.mesh.predict_next(bob, [bob_cards[0].card_id])
    assert bob_prediction.candidates[0][0] == bob_cards[1].card_id
    assert all(candidate_id not in {card.card_id for card in alice_cards} for candidate_id, _ in bob_prediction.candidates)


def test_retrieval_competition_favors_more_activated_candidate() -> None:
    clock = FakeClock()
    index = _index(clock)
    namespace = _namespace()
    first = index.capture_interaction(namespace, "alpha repeated cue", trust=0.9, salience=0.9)
    second = index.capture_interaction(namespace, "alpha weaker alternative", trust=0.5, salience=0.5)
    # Re-exposure increases storage strength for the first candidate.
    index.capture_interaction(namespace, "alpha repeated cue", trust=0.9, salience=0.9)
    hits = index.search(namespace, "alpha", limit=10)
    assert {first.card_id, second.card_id}.issubset({hit.card.card_id for hit in hits})
    p_first = index.retrieval_competition(hits, first.card_id)
    p_second = index.retrieval_competition(hits, second.card_id)
    assert 0.0 < p_first < 1.0
    assert 0.0 < p_second < 1.0
    assert p_first > p_second
