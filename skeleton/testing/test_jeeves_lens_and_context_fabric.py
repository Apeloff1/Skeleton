from skeleton.jeeves.agent.context_fabric import (
    CognitiveContextFabric,
    RepositoryContextAdapter,
)
from skeleton.jeeves.agent.context_repository import (
    ContextEntry,
    ContextKind,
    ContextNamespace,
    ContextPatch,
    ContextPatchItem,
    ContextRepository,
    PatchOperation,
)
from skeleton.jeeves.agent.lens_system import (
    DirectionLedger,
    LensFamily,
    SemanticLensRouter,
)
from skeleton.jeeves.agent.memory_game_index import CardKind, MemoryGameIndex, SourceTier
from skeleton.jeeves.agent.types import stable_id


def _entry(namespace, key, content, now=100.0):
    return ContextEntry(
        entry_id=stable_id("entry", {"key": key}),
        namespace=namespace,
        key=key,
        kind=ContextKind.EPISODIC,
        content=content,
        created_at=now,
        updated_at=now,
        confidence=0.9,
        salience=0.8,
        trust=0.95,
        source="test",
        tags=("narrative",),
    )


def _repo():
    namespace = ContextNamespace("tenant", "user", "workspace")
    repo = ContextRepository(namespace, clock=lambda: 100.0)
    first = _entry(namespace, "scene-a", "A character looks toward the red door.")
    second = _entry(namespace, "scene-b", "The next shot shows the red door opening.")
    patch = ContextPatch(
        patch_id=stable_id("patch", {"entries": [first.content_fingerprint, second.content_fingerprint]}),
        namespace=namespace,
        items=(
            ContextPatchItem(PatchOperation.UPSERT, first.key, entry=first, reason="fixture"),
            ContextPatchItem(PatchOperation.UPSERT, second.key, entry=second, reason="fixture"),
        ),
        author="test",
        created_at=100.0,
        rationale="fixture",
    )
    repo.commit("main", patch, message="fixture", expected_head=None)
    return repo, first, second


def test_cinema_lenses_surface_juxtaposition_and_pov_without_calling_them_facts():
    router = SemanticLensRouter()
    bundle = router.route(
        "Use juxtaposition and POV gaze between a reaction shot and a door",
        adjacent_text=("character looks left", "door opens"),
        limit=12,
    )
    ids = set(bundle.ids())
    assert "kuleshov_juxtaposition" in ids
    assert "pov_gaze" in ids
    cinema = [item for item in bundle.activations if item.lens.family is LensFamily.CINEMA]
    assert cinema
    assert all(item.lens.preserves_source_truth for item in cinema)


def test_literary_and_game_lenses_are_perpendicular_families():
    router = SemanticLensRouter()
    bundle = router.route(
        "An unreliable narrator uses a foil while the player bluffs under fog of war and controls tempo",
        limit=16,
    )
    families = set(bundle.families)
    assert LensFamily.LITERARY in families
    assert LensFamily.LUDIC in families
    ids = set(bundle.ids())
    assert "unreliable_narration" in ids
    assert "partial_observability" in ids


def test_direction_ledger_preserves_tangents_across_restart_boundaries():
    ledger = DirectionLedger()
    root = ledger.add(
        axis="memory",
        hypothesis="cue cards should precede narrative retrieval",
        next_probe="measure fast-hit precision",
        priority=0.9,
    )
    child = ledger.add(
        parent_id=root.direction_id,
        axis="cinematic semantics",
        hypothesis="juxtaposition pairs can improve relation recall",
        next_probe="ablate pair relations",
        priority=0.8,
    )
    assert ledger.resume_queue()[0].direction_id == root.direction_id
    assert ledger.children(root.direction_id)[0].direction_id == child.direction_id
    assert ledger.fingerprint


def test_context_fabric_rehydrates_canonical_content_and_flags_stale_card():
    repo, first, second = _repo()
    index = MemoryGameIndex(clock=lambda: 100.0)
    stale = index.index_source(
        namespace_key=repo.namespace.key,
        source_tier=SourceTier.CONTEXT_REPOSITORY,
        source_ref=first.key,
        source_fingerprint="0" * 64,
        cue="character red door",
        preview="STALE PREVIEW SHOULD NOT WIN",
        kind=CardKind.EPISODE_CUE,
        trust=1.0,
        confidence=1.0,
    )
    fabric = CognitiveContextFabric(index=index)
    fabric.register(RepositoryContextAdapter(repo, branch="main"))
    result = fabric.retrieve(repo.namespace.key, "character looks at red door juxtaposition")
    assert stale.card_id in result.stale_card_ids
    assert any(record.content == first.content for record in result.records)
    assert all(record.content != "STALE PREVIEW SHOULD NOT WIN" for record in result.records)
    assert result.broad_search_used is True
    assert "kuleshov_juxtaposition" in set(result.lenses.ids())


def test_deep_results_are_reindexed_as_source_cues_for_next_fast_pass():
    repo, first, second = _repo()
    fabric = CognitiveContextFabric(index=MemoryGameIndex(clock=lambda: 100.0))
    fabric.register(RepositoryContextAdapter(repo, branch="main"))
    first_pass = fabric.retrieve(repo.namespace.key, "red door opening")
    assert first_pass.records
    count_after = fabric.index.count(repo.namespace.key)
    assert count_after >= 1
    second_pass = fabric.retrieve(repo.namespace.key, "red door")
    assert second_pass.fast_recall.direct_hits
