from __future__ import annotations

import math

from skeleton.jeeves.agent.context_pipeline import LayeredContextResolver, ResolutionPolicy
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGameIndex
from skeleton.jeeves.agent.relational_memory import (
    RelationKind,
    RelationalMemoryIndex,
    RelationalMemoryPolicy,
)


class Clock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def tick(self, seconds: float = 1.0) -> float:
        self.value += seconds
        return self.value


def _fixture():
    clock = Clock()
    namespace = MemoryNamespace("tenant", "user", session_id="session")
    cards = MemoryGameIndex(clock=clock)
    relations = RelationalMemoryIndex(cards, clock=clock)
    return clock, namespace, cards, relations


def test_unordered_relations_canonicalize_but_succession_keeps_direction():
    clock, ns, cards, relations = _fixture()
    a = cards.capture_interaction(ns, "alpha state")
    clock.tick()
    b = cards.capture_interaction(ns, "beta state")

    left = relations.link(ns, RelationKind.ADJACENCY, (a.card_id, b.card_id))
    right = relations.link(ns, RelationKind.ADJACENCY, (b.card_id, a.card_id))
    assert left.relation_id == right.relation_id
    assert relations.store.get(left.relation_id).occurrence_count == 2

    forward = relations.link(ns, RelationKind.SUCCESSION, (a.card_id, b.card_id))
    backward = relations.link(ns, RelationKind.SUCCESSION, (b.card_id, a.card_id))
    assert forward.relation_id != backward.relation_id


def test_transition_prediction_is_normalized_over_known_support_and_open_world():
    _, ns, cards, relations = _fixture()
    a = cards.capture_interaction(ns, "alpha")
    b = cards.capture_interaction(ns, "beta")
    c = cards.capture_interaction(ns, "gamma")
    for _ in range(4):
        relations.link(ns, RelationKind.SUCCESSION, (a.card_id, b.card_id))
    relations.link(ns, RelationKind.SUCCESSION, (a.card_id, c.card_id))

    prediction = relations.predictions(ns, a.card_id)
    assert len(prediction) == 2
    assert math.isclose(sum(item.probability for item in prediction), 1.0)
    assert all(item.closed_support is False for item in prediction)
    assert prediction[0].target_card_id == b.card_id
    assert prediction[0].support_weight > prediction[1].support_weight


def test_cold_start_is_not_scored_as_failed_prediction():
    _, ns, cards, relations = _fixture()
    a = cards.capture_interaction(ns, "alpha")
    b = cards.capture_interaction(ns, "beta")

    feedback = relations.record_transition(ns, a.card_id, b.card_id)
    assert feedback.prediction_available is False
    assert feedback.surprise == 0.0
    assert feedback.brier_error == 0.0


def test_unexpected_supported_transition_can_mark_event_boundary():
    _, ns, cards, relations = _fixture()
    a = cards.capture_interaction(ns, "alpha")
    expected = cards.capture_interaction(ns, "expected beta")
    unexpected = cards.capture_interaction(ns, "unexpected gamma")

    for _ in range(200):
        relations.link(ns, RelationKind.SUCCESSION, (a.card_id, expected.card_id))

    observation = relations.observe_stream_step(
        ns,
        unexpected.card_id,
        previous_card_ids=(a.card_id,),
    )
    assert observation.event_boundary_ids
    boundary = relations.store.get(observation.event_boundary_ids[0])
    assert boundary is not None
    assert boundary.kind is RelationKind.EVENT_BOUNDARY
    assert boundary.metadata["prediction_available"] is True


def test_stream_learning_builds_aba_motif_without_lookahead():
    _, ns, cards, relations = _fixture()
    a = cards.capture_interaction(ns, "alpha")
    b = cards.capture_interaction(ns, "beta")

    first = relations.observe_stream_step(ns, b.card_id, previous_card_ids=(a.card_id,))
    assert not first.event_boundary_ids
    second = relations.observe_stream_step(
        ns,
        a.card_id,
        previous_card_ids=(a.card_id, b.card_id),
    )
    traces = relations.store.list_namespace(ns)
    motifs = [item for item in traces if item.kind is RelationKind.MOTIF]
    assert motifs
    assert motifs[0].card_ids == (a.card_id, b.card_id, a.card_id)
    assert second.fingerprint


def test_relation_search_preserves_card_and_relation_provenance():
    _, ns, cards, relations = _fixture()
    a = cards.capture_interaction(ns, "blue door clue", provenance=("evidence:a",))
    b = cards.capture_interaction(ns, "red room response", provenance=("evidence:b",))
    relations.link(
        ns,
        RelationKind.JUXTAPOSITION,
        (a.card_id, b.card_id),
        provenance=("relation:trial",),
        rationale="paired interpretation changed",
    )

    seeds = cards.search(ns, "blue door", minimum_score=0.0)
    hits = relations.search(ns, "blue door relation", seeds)
    assert hits
    assert {"evidence:a", "evidence:b", "relation:trial"}.issubset(set(hits[0].evidence_ids))


def test_namespace_isolation_applies_to_relations():
    _, ns, cards, relations = _fixture()
    other = MemoryNamespace("tenant", "other-user", session_id="session")
    a = cards.capture_interaction(ns, "shared cue alpha")
    b = cards.capture_interaction(ns, "shared cue beta")
    x = cards.capture_interaction(other, "shared cue alpha")
    y = cards.capture_interaction(other, "shared cue beta")
    relations.link(ns, RelationKind.ADJACENCY, (a.card_id, b.card_id))
    relations.link(other, RelationKind.ADJACENCY, (x.card_id, y.card_id))

    seeds = cards.search(ns, "shared cue", minimum_score=0.0)
    hits = relations.search(ns, "shared cue", seeds)
    assert hits
    assert all(hit.trace.namespace.key == ns.key for hit in hits)


def test_context_resolver_queries_relations_before_scoped_memory():
    clock, ns, cards, relations = _fixture()
    memory = MemoryManager(clock=clock)
    a = cards.capture_interaction(ns, "blue door")
    b = cards.capture_interaction(ns, "red room")
    relations.link(ns, RelationKind.JUXTAPOSITION, (a.card_id, b.card_id))
    resolver = LayeredContextResolver(
        cards=cards,
        relations=relations,
        memory=memory,
        policy=ResolutionPolicy(
            minimum_item_score=0.0,
            stop_coverage=1.0,
            stop_confidence=1.0,
            stop_trust=1.0,
        ),
    )

    result = resolver.resolve(ns, "blue door")
    sources = [stage.source for stage in result.stages]
    assert sources[0] == "memory_game"
    assert sources[1] == "relational_memory"
    assert sources.index("relational_memory") < sources.index("scoped_memory")
    assert any(item.source == "relational_memory" for item in result.items)


def test_semantic_pair_is_tagged_as_hypothesis_not_evidence_promotion():
    _, ns, cards, relations = _fixture()
    a = cards.capture_interaction(ns, "face neutral")
    b = cards.capture_interaction(ns, "coffin image")
    trace = relations.register_semantic_pair(
        ns,
        a.card_id,
        b.card_id,
        relation=RelationKind.JUXTAPOSITION,
        rationale="Kuleshov-style candidate relation",
        confidence=0.7,
    )
    assert trace.metadata["semantic_hypothesis"] is True
    assert trace.kind is RelationKind.JUXTAPOSITION
