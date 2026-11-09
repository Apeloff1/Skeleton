from __future__ import annotations

from skeleton.jeeves.agent.context_pipeline import (
    ContextSourceAdapter,
    ContextSourceKind,
    ContextTier,
    LayeredContextResolver,
    ResolutionPolicy,
    SourceRecord,
)
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGameIndex, MemoryGamePolicy
from skeleton.jeeves.agent.semantic_lenses import (
    JuxtapositionAnalyzer,
    LensFamily,
    SemanticLensRouter,
    SemanticObservation,
    TangentSeed,
)
from skeleton.jeeves.agent.tangent_graph import ExplorationAxis, TangentGraph, TangentState


def _namespace() -> MemoryNamespace:
    return MemoryNamespace("tenant", "user", "workspace", "session")


def test_semantic_router_prefers_perpendicular_family_coverage() -> None:
    observations = (
        SemanticObservation("a", "The player sees a hidden warning before the scene changes.", 0, tags=("game", "scene")),
        SemanticObservation("b", "The narrator says everything is safe, but the warning remains.", 1, tags=("narrator", "contrast")),
        SemanticObservation("c", "Later the same warning appears again after a costly player choice.", 2, tags=("repeat", "choice")),
    )
    selection = SemanticLensRouter().select(observations, max_lenses=8, max_per_family=2, perpendicular=True)
    assert len(selection.lenses) >= 4
    assert len(selection.families) >= 4
    assert len({lens.family for lens in selection.lenses}) >= 4
    assert any(lens.family is LensFamily.FILM for lens in selection.lenses)
    assert any(lens.family in {LensFamily.GAME, LensFamily.NARRATIVE, LensFamily.LITERATURE} for lens in selection.lenses)


def test_juxtaposition_detects_context_shift_without_claiming_truth() -> None:
    left = SemanticObservation("left", "The system reports the deployment is safe.", 0, tags=("safe", "system"))
    right = SemanticObservation("right", "However the rollback alarm is active and the health check failed.", 1, tags=("failure", "alarm"))
    signal = JuxtapositionAnalyzer.compare(left, right)
    assert signal.changed_context
    assert signal.contrast_signal > 0.4
    assert signal.novelty_signal > 0.3
    assert signal.left_id == "left"
    assert signal.right_id == "right"


def test_tangent_frontier_keeps_perpendicular_directions_and_restart_state() -> None:
    graph = TangentGraph()
    root = "root-fingerprint"
    seeds = (
        ("s1", "causal alternative", ExplorationAxis.CAUSAL, LensFamily.SYSTEM),
        ("s2", "film contrast", ExplorationAxis.CINEMATIC, LensFamily.FILM),
        ("s3", "game strategy", ExplorationAxis.LUDIC, LensFamily.GAME),
        ("s4", "memory cue", ExplorationAxis.MEMORY, LensFamily.COGNITIVE),
    )
    ids = []
    for index, (seed_id, direction, axis, family) in enumerate(seeds):
        seed = TangentSeed(seed_id, root, "test", direction, "keep the side direction", 0.8, 0.7)
        node = graph.add_seed(seed, axis=axis, family=family, sequence=index)
        ids.append(node.tangent_id)
    frontier = graph.frontier(limit=4, max_per_axis=1, max_per_family=1)
    assert set(frontier.tangent_ids) == set(ids)
    assert len(frontier.axes) == 4
    graph.update_state(ids[0], TangentState.ACTIVE, sequence=10)
    bundle = graph.checkpoint(root_fingerprint=root, sequence=11)
    assert ids[0] in bundle.active_ids
    assert graph.fingerprint == bundle.graph_fingerprint


def test_context_pipeline_uses_index_cards_before_deep_sources() -> None:
    namespace = _namespace()
    cards = MemoryGameIndex(
        policy=MemoryGamePolicy(
            minimum_score=0.0,
            minimum_fast_path_coverage=0.0,
            minimum_fast_path_confidence=0.0,
        )
    )
    cards.capture_interaction(
        namespace,
        "User prefers deterministic replay evidence for release checks.",
        context_tags=("release", "evidence"),
        trust=0.95,
        salience=0.95,
    )
    calls = {"journal": 0}

    def journal_search(query: str, limit: int, tags: tuple[str, ...]):
        calls["journal"] += 1
        return ()

    resolver = LayeredContextResolver(
        cards=cards,
        memory=MemoryManager(),
        adapters=(ContextSourceAdapter("journal", ContextSourceKind.JOURNAL, journal_search),),
        policy=ResolutionPolicy(
            minimum_item_score=0.0,
            stop_coverage=0.0,
            stop_confidence=0.0,
            stop_trust=0.0,
            maximum_tier=ContextTier.ARCHIVE,
        ),
    )
    result = resolver.resolve(namespace, "deterministic replay evidence", context_tags=("release",))
    assert result.fast_path
    assert result.stopped_at is ContextTier.INDEX_CARD
    assert calls["journal"] == 0
    assert result.items[0].tier is ContextTier.INDEX_CARD


def test_context_pipeline_deepens_only_until_sufficient_structured_context() -> None:
    namespace = _namespace()
    cards = MemoryGameIndex()
    calls = {"cache": 0, "journal": 0}

    def cache_search(query: str, limit: int, tags: tuple[str, ...]):
        calls["cache"] += 1
        return (
            SourceRecord(
                "cache-1",
                "cache",
                ContextSourceKind.CACHE,
                "replication rollback contract",
                relevance=1.0,
                trust=0.95,
                confidence=0.95,
                cost=0.05,
            ),
        )

    def journal_search(query: str, limit: int, tags: tuple[str, ...]):
        calls["journal"] += 1
        return (
            SourceRecord(
                "journal-1",
                "journal",
                ContextSourceKind.JOURNAL,
                "old narrative record about replication",
                relevance=0.8,
                trust=0.7,
                confidence=0.7,
                cost=0.7,
            ),
        )

    resolver = LayeredContextResolver(
        cards=cards,
        memory=MemoryManager(),
        adapters=(
            ContextSourceAdapter("cache", ContextSourceKind.CACHE, cache_search),
            ContextSourceAdapter("journal", ContextSourceKind.JOURNAL, journal_search),
        ),
        policy=ResolutionPolicy(
            minimum_item_score=0.0,
            stop_coverage=0.60,
            stop_confidence=0.70,
            stop_trust=0.70,
            minimum_deep_gain=0.0,
        ),
    )
    result = resolver.resolve(namespace, "replication rollback contract")
    assert not result.fast_path
    assert calls["cache"] == 1
    assert calls["journal"] == 0
    assert result.stopped_at is ContextTier.CACHE
    assert any(item.item_id == "cache-1" for item in result.items)


def test_context_resolution_sections_do_not_duplicate_scoped_memory() -> None:
    namespace = _namespace()
    memory = MemoryManager()
    memory.remember(namespace, "alpha beta gamma", trust=0.9, salience=0.9)
    resolver = LayeredContextResolver(
        cards=MemoryGameIndex(),
        memory=memory,
        policy=ResolutionPolicy(stop_coverage=1.0, stop_confidence=1.0, stop_trust=1.0, maximum_tier=ContextTier.SCOPED_MEMORY),
    )
    result = resolver.resolve(namespace, "alpha beta gamma")
    assert any(item.tier is ContextTier.SCOPED_MEMORY for item in result.items)
    assert all(section.name != "context_scoped_memory" for section in result.sections())
