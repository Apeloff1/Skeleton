from skeleton.jeeves.agent.cognition import ContextCompiler
from skeleton.jeeves.agent.context_fabric import CognitiveContextFabric, ContextFabricPolicy
from skeleton.jeeves.agent.evidence import EvidenceLedger
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game_index import CardKind, SourceTier
from skeleton.jeeves.agent.types import Goal


def test_context_fabric_policy_is_constructible_with_fast_hit_gate():
    policy = ContextFabricPolicy(minimum_fast_hits_before_skip_deep=2)
    assert policy.minimum_fast_hits_before_skip_deep == 2


def test_context_compiler_uses_fast_cards_then_canonical_rehydration_not_legacy_memory_section():
    namespace = MemoryNamespace("tenant", "user", "workspace", "session")
    memory = MemoryManager()
    record = memory.remember(
        namespace,
        "User prefers evidence-first deterministic compiler validation.",
        trust=1.0,
        salience=0.9,
        source="user-interaction",
        tags=("compiler", "evidence"),
    )
    fabric = CognitiveContextFabric()
    fabric.index.index_source(
        namespace_key=namespace.key,
        source_tier=SourceTier.MEMORY_STORE,
        source_ref=record.memory_id,
        source_fingerprint=record.fingerprint,
        cue=record.content,
        preview=record.content,
        kind=CardKind.INTERACTION,
        trust=record.trust,
        confidence=record.trust,
        salience=record.salience,
    )
    packet = ContextCompiler().compile(
        system_instruction="system",
        task_instruction="plan the compiler work",
        goal=Goal("goal-context-fabric", "deterministic compiler evidence"),
        namespace=namespace,
        memory=memory,
        evidence=EvidenceLedger(),
        context_fabric=fabric,
    )
    names = set(packet.retained_sections)
    assert "fast_memory_index" in names
    assert "canonical_context" in names
    assert "memory" not in names
    fast = next(section for section in packet.sections if section.name == "fast_memory_index")
    canonical = next(section for section in packet.sections if section.name == "canonical_context")
    assert canonical.priority > fast.priority
    assert record.content not in fast.content
    assert '"authoritative":false' in fast.content
    assert record.memory_id in canonical.content
    assert record.content in canonical.content


def test_interpretive_lenses_are_explicitly_marked_non_evidence_in_model_context():
    namespace = MemoryNamespace("tenant", "user", "workspace", "session")
    memory = MemoryManager()
    record = memory.remember(
        namespace,
        "A neutral reaction shot is followed by a frightening scene.",
        trust=0.9,
        salience=0.8,
        source="scene-note",
        tags=("juxtaposition", "reaction"),
    )
    fabric = CognitiveContextFabric()
    fabric.index.index_source(
        namespace_key=namespace.key,
        source_tier=SourceTier.MEMORY_STORE,
        source_ref=record.memory_id,
        source_fingerprint=record.fingerprint,
        cue="juxtaposition reaction shot frightening scene",
        preview=record.content,
        trust=record.trust,
        confidence=record.trust,
        salience=record.salience,
    )
    packet = ContextCompiler().compile(
        system_instruction="system",
        task_instruction="analyze juxtaposition without inventing facts",
        goal=Goal("goal-lens-context", "juxtaposition reaction shot"),
        namespace=namespace,
        memory=memory,
        evidence=EvidenceLedger(),
        context_fabric=fabric,
    )
    section = next(item for item in packet.sections if item.name == "semantic_lenses")
    assert '"interpretive_only":true' in section.content
    assert '"factual_assertion_authorized":false' in section.content
    assert '"causal_assertion_authorized":false' in section.content
    assert "not factual evidence" in section.content
