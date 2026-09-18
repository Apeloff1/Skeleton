from __future__ import annotations

from skeleton.jeeves.agent.associative_memory import AssociationKind, AssociativeMemoryMesh
from skeleton.jeeves.agent.context_pipeline import (
    ContextSourceAdapter,
    ContextSourceKind,
    ContextTier,
    LayeredContextResolver,
    ResolutionPolicy,
)
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGameIndex, MemoryGamePolicy
from skeleton.jeeves.agent.nuance_runtime import NuanceRuntimePolicy, ScientificNuanceRuntime
from skeleton.jeeves.agent.tangent_graph import ExplorationAxis


class TickClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


def _namespace() -> MemoryNamespace:
    return MemoryNamespace("tenant", "user", "workspace", "session")


def test_associative_l0_can_complete_fast_context_before_journal_without_inflating_trust() -> None:
    namespace = _namespace()
    clock = TickClock()
    cards = MemoryGameIndex(
        policy=MemoryGamePolicy(
            minimum_score=0.0,
            minimum_fast_path_coverage=1.0,
            minimum_fast_path_confidence=1.0,
        ),
        clock=clock,
    )
    mesh = AssociativeMemoryMesh(clock=clock)
    anchor = cards.capture_interaction(
        namespace,
        "alpha release deterministic replay contract",
        trust=0.96,
        salience=0.95,
    )
    target = cards.capture_interaction(
        namespace,
        "beta correction",
        trust=0.20,
        salience=0.55,
    )
    mesh.observe(
        namespace,
        anchor.card_id,
        target.card_id,
        kind=AssociationKind.CORRECTION,
        strength=1.0,
        surprise=0.9,
        direction_confidence=1.0,
    )

    calls = {"journal": 0}

    def journal_search(query: str, limit: int, tags: tuple[str, ...]):
        calls["journal"] += 1
        return ()

    resolver = LayeredContextResolver(
        cards=cards,
        associations=mesh,
        memory=MemoryManager(clock=clock),
        adapters=(ContextSourceAdapter("journal", ContextSourceKind.JOURNAL, journal_search),),
        policy=ResolutionPolicy(
            card_limit=1,
            association_seed_limit=1,
            association_limit_per_seed=4,
            minimum_item_score=0.0,
            minimum_association_score=0.0,
            stop_coverage=0.50,
            stop_confidence=0.0,
            stop_trust=0.0,
            minimum_deep_gain=0.0,
            maximum_tier=ContextTier.ARCHIVE,
        ),
    )

    result = resolver.resolve(namespace, "alpha release deterministic replay contract beta correction")
    by_id = {item.item_id: item for item in result.items}

    assert result.fast_path
    assert result.stopped_at is ContextTier.INDEX_CARD
    assert calls["journal"] == 0
    assert anchor.card_id in by_id
    assert target.card_id in by_id
    assert by_id[target.card_id].source == "associative:correction"
    assert by_id[target.card_id].trust == target.trust == 0.20
    assert by_id[target.card_id].metadata["trust_inherited_from_target_only"] is True


def test_nuance_prepare_resolves_before_capture_and_links_preexisting_interactions() -> None:
    namespace = _namespace()
    clock = TickClock()
    cards = MemoryGameIndex(policy=MemoryGamePolicy(minimum_score=0.0), clock=clock)
    mesh = AssociativeMemoryMesh(clock=clock)
    first = cards.capture_interaction(namespace, "The player sees a warning.", context_tags=("game",))
    second = cards.capture_interaction(namespace, "A montage cut reframes the warning.", context_tags=("film",))
    resolver = LayeredContextResolver(
        cards=cards,
        associations=mesh,
        memory=MemoryManager(clock=clock),
        policy=ResolutionPolicy(
            minimum_item_score=0.0,
            stop_coverage=1.0,
            stop_confidence=1.0,
            stop_trust=1.0,
            maximum_tier=ContextTier.SCOPED_MEMORY,
        ),
    )
    runtime = ScientificNuanceRuntime(
        resolver,
        policy=NuanceRuntimePolicy(link_recent_cards=2),
    )

    frame = runtime.prepare(
        namespace,
        "The narrator contradicts the player after a juxtaposition montage cut.",
        context_tags=("film", "game", "narrator"),
    )

    assert frame.captured_card_id is not None
    assert frame.captured_card_id not in {item.item_id for item in frame.context.items}
    assert frame.juxtaposition_signals
    assert frame.observations[0].source == "current-user-input"
    assert frame.observations[0].fingerprint
    assert {first.card_id, second.card_id}.issubset(
        {hit.association.source_card_id for hit in mesh.neighbors(namespace, first.card_id)}
        | {first.card_id, second.card_id}
    )
    incoming_from_second = {
        hit.association.target_card_id
        for hit in mesh.neighbors(namespace, second.card_id)
        if hit.association.kind in {AssociationKind.TEMPORAL_FORWARD, AssociationKind.CONTEXT_SHIFT}
    }
    assert frame.captured_card_id in incoming_from_second


def test_sequence_prediction_uses_preexisting_trace_not_current_self_hit() -> None:
    namespace = _namespace()
    clock = TickClock()
    cards = MemoryGameIndex(policy=MemoryGamePolicy(minimum_score=0.0), clock=clock)
    mesh = AssociativeMemoryMesh(clock=clock)
    a = cards.capture_interaction(namespace, "alpha step")
    b = cards.capture_interaction(namespace, "beta step")
    c = cards.capture_interaction(namespace, "gamma expected continuation")
    mesh.observe_sequence(namespace, (a.card_id, b.card_id, c.card_id))

    # Make A,B the two most recently exposed cards while preserving the old
    # A->B->C sequence as the historical prediction trace.
    cards.capture_interaction(namespace, "alpha step")
    cards.capture_interaction(namespace, "beta step")

    resolver = LayeredContextResolver(
        cards=cards,
        associations=mesh,
        memory=MemoryManager(clock=clock),
        policy=ResolutionPolicy(
            minimum_item_score=0.0,
            stop_coverage=1.0,
            stop_confidence=1.0,
            stop_trust=1.0,
            maximum_tier=ContextTier.SCOPED_MEMORY,
        ),
    )
    runtime = ScientificNuanceRuntime(resolver, policy=NuanceRuntimePolicy(link_recent_cards=2))
    frame = runtime.prepare(namespace, "delta current input")

    assert frame.sequence_prediction is not None
    assert frame.sequence_prediction.evidence_count > 0
    assert frame.sequence_prediction.candidates[0][0] == c.card_id
    assert frame.captured_card_id not in {candidate for candidate, _ in frame.sequence_prediction.candidates}


def test_restart_without_model_findings_still_preserves_perpendicular_lens_directions() -> None:
    namespace = _namespace()
    clock = TickClock()
    cards = MemoryGameIndex(policy=MemoryGamePolicy(minimum_score=0.0), clock=clock)
    resolver = LayeredContextResolver(
        cards=cards,
        memory=MemoryManager(clock=clock),
        policy=ResolutionPolicy(maximum_tier=ContextTier.SCOPED_MEMORY),
    )
    runtime = ScientificNuanceRuntime(
        resolver,
        policy=NuanceRuntimePolicy(
            minimum_perpendicular_activation=0.20,
            max_perpendicular_tangents=8,
        ),
    )
    frame = runtime.prepare(
        namespace,
        (
            "A montage juxtaposition reframes the narrator while a player breaks a rule, "
            "the motif repeats later, and memory cues contradict the apparent sequence."
        ),
        context_tags=("film", "literature", "game", "memory", "sequence"),
    )

    packet = runtime.checkpoint_before_restart(frame.frame_id, sequence=7)
    frontier = packet.frontier

    assert frontier.tangent_ids
    assert len(frontier.axes) >= 3
    assert ExplorationAxis.CINEMATIC in frontier.axes
    assert ExplorationAxis.LUDIC in frontier.axes
    assert all(
        runtime.tangent_bridge.graph.get(tangent_id).evidence_ids == ()
        for tangent_id in frontier.tangent_ids
    )


def test_semantic_observation_identity_is_position_and_source_sensitive() -> None:
    from skeleton.jeeves.agent.semantic_lenses import SemanticObservation

    base = SemanticObservation("obs", "same content", 0, source="diary", tags=("x",))
    moved = SemanticObservation("obs", "same content", 1, source="diary", tags=("x",))
    resourced = SemanticObservation("obs", "same content", 0, source="current-input", tags=("x",))

    assert base.fingerprint == SemanticObservation("obs", "same content", 0, source="diary", tags=("x",)).fingerprint
    assert base.fingerprint != moved.fingerprint
    assert base.fingerprint != resourced.fingerprint
