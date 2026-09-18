from __future__ import annotations

import pytest

from skeleton.jeeves.agent.associative_memory import AssociationKind, AssociativeMemoryGameIndex
from skeleton.jeeves.agent.context_acquisition import InteractionAcquisitionEngine, build_cue_first_context_system
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGamePolicy


class FakeClock:
    def __init__(self, value: float = 1_000_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float = 1.0) -> None:
        self.value += seconds


def _namespace(user: str = "user") -> MemoryNamespace:
    return MemoryNamespace("tenant", user, "workspace", "session")


def _engine(clock: FakeClock) -> InteractionAcquisitionEngine:
    cards = AssociativeMemoryGameIndex(
        policy=MemoryGamePolicy(minimum_score=0.0),
        clock=clock,
    )
    return InteractionAcquisitionEngine(cards)


def test_streaming_acquisition_records_each_adjacent_pair_once() -> None:
    clock = FakeClock()
    engine = _engine(clock)
    ns = _namespace()
    first = engine.capture(ns, "Open the repository.", context_tags=("repo",))
    clock.advance()
    second = engine.capture(ns, "Inspect the tests.", context_tags=("test",))
    neighbors = engine.cards.mesh.neighbors(
        ns, first.card.card_id, kinds=(AssociationKind.TEMPORAL_FORWARD,)
    )
    assert len(neighbors) == 1
    assert neighbors[0].association.target_card_id == second.card.card_id
    assert neighbors[0].association.observations == 1

    clock.advance()
    third = engine.capture(ns, "Run validation.", context_tags=("validation",))
    neighbors_after = engine.cards.mesh.neighbors(
        ns, first.card.card_id, kinds=(AssociationKind.TEMPORAL_FORWARD,)
    )
    assert neighbors_after[0].association.observations == 1
    prediction = engine.cards.mesh.predict_next(ns, (first.card.card_id, second.card.card_id))
    assert prediction.candidates
    assert prediction.candidates[0][0] == third.card.card_id


def test_context_shift_and_juxtaposition_are_relational_not_truth_updates() -> None:
    clock = FakeClock()
    engine = _engine(clock)
    ns = _namespace()
    first = engine.capture(
        ns,
        "A neutral face is shown beside a warm meal.",
        context_tags=("film", "meal"),
        trust=0.71,
    )
    clock.advance()
    second = engine.capture(
        ns,
        "The same neutral face is shown beside a funeral image.",
        context_tags=("film", "funeral"),
        trust=0.68,
    )
    assert second.context_shift_score > 0.0
    assert second.juxtaposition_score > 0.0
    kinds = {hit.association.kind for hit in engine.cards.mesh.neighbors(ns, first.card.card_id)}
    assert AssociationKind.CONTEXT_SHIFT in kinds
    assert AssociationKind.JUXTAPOSITION in kinds
    stored = engine.cards.store.get(second.card.card_id)
    assert stored is not None
    assert stored.trust == pytest.approx(0.68)


def test_correction_creates_revision_candidate_without_overwriting_previous_card() -> None:
    clock = FakeClock()
    engine = _engine(clock)
    ns = _namespace()
    old = engine.capture(ns, "The preferred format is CSV.", context_tags=("preference",))
    clock.advance()
    new = engine.capture(ns, "Actually, the preferred format is Parquet.", context_tags=("preference",))
    correction = engine.cards.mesh.neighbors(
        ns, old.card.card_id, kinds=(AssociationKind.CORRECTION,)
    )
    assert correction
    assert correction[0].association.target_card_id == new.card.card_id
    assert correction[0].association.metadata["revision_candidate"] is True
    assert correction[0].association.metadata["authoritative"] is False
    assert engine.cards.store.get(old.card.card_id) is not None
    assert engine.cards.store.get(new.card.card_id) is not None


def test_user_namespaces_do_not_share_cards_or_associations() -> None:
    clock = FakeClock()
    engine = _engine(clock)
    alice = _namespace("alice")
    bob = _namespace("bob")
    a = engine.capture(alice, "Alice private deployment preference.", context_tags=("private",))
    clock.advance()
    engine.capture(alice, "Alice second private cue.", context_tags=("private",))
    b = engine.capture(bob, "Bob unrelated preference.", context_tags=("private",))
    assert engine.recent_card_ids(alice) != engine.recent_card_ids(bob)
    assert engine.cards.mesh.neighbors(bob, a.card.card_id) == ()
    bob_hits = engine.cards.search(bob, "Alice deployment", limit=20)
    assert a.card.card_id not in {hit.card.card_id for hit in bob_hits}
    assert b.card.card_id in {card.card_id for card in engine.cards.store.namespace_cards(bob)}


def test_factory_guarantees_shared_associative_l0_before_deep_context() -> None:
    system = build_cue_first_context_system(memory=MemoryManager())
    assert system.resolver.cards is system.cards
    assert system.compiler.resolver is system.resolver
    assert system.acquisition.cards is system.cards
    assert system.acquisition.resolver is system.resolver
    assert isinstance(system.cards, AssociativeMemoryGameIndex)
