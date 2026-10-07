from skeleton.jeeves.agent.context_fabric import CognitiveContextFabric, MemoryManagerAdapter
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game_index import CardKind, SourceTier


def test_interaction_card_rehydrates_from_canonical_memory_store():
    namespace = MemoryNamespace(
        tenant_id="tenant",
        user_id="user",
        workspace_id="workspace",
        session_id="session",
    )
    memory = MemoryManager()
    record = memory.remember(
        namespace,
        "User wants the compiler regression investigated first.",
        trust=1.0,
        salience=0.9,
        source="user-interaction",
        tags=("interaction", "compiler"),
    )

    fabric = CognitiveContextFabric()
    card = fabric.index.remember_interaction(
        namespace_key=namespace.key,
        turn_id="turn-1",
        text=record.content,
        source_ref=record.memory_id,
        source_fingerprint=record.fingerprint,
        sequence=1,
        source_tier=SourceTier.MEMORY_STORE,
        source_provider=f"memory-store:{namespace.key}",
        role="user",
        trust=record.trust,
        salience=record.salience,
        tags=record.tags,
    )

    result = fabric.retrieve(
        namespace.key,
        "compiler regression",
        call_adapters=(MemoryManagerAdapter(memory, namespace),),
    )

    assert card.kind is CardKind.INTERACTION
    assert card.source_tier is SourceTier.MEMORY_STORE
    assert result.fast_recall.direct_hits
    assert result.fast_recall.direct_hits[0].card.card_id == card.card_id
    assert any(item.source_ref == record.memory_id for item in result.records)
    assert record.memory_id not in result.unresolved_source_refs
    assert card.card_id not in result.stale_card_ids
