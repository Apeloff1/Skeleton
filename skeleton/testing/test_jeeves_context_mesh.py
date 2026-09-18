from __future__ import annotations

from skeleton.jeeves.agent.context_fabric import (
    CallableContextAdapter,
    CognitiveContextFabric,
    DeepContextRecord,
)
from skeleton.jeeves.agent.context_mesh import ContextRepositoryMesh
from skeleton.jeeves.agent.context_repository import (
    ContextEntry,
    ContextKind,
    ContextNamespace,
    ContextPatch,
    ContextPatchItem,
    ContextRepository,
    PatchOperation,
)
from skeleton.jeeves.agent.memory_game_index import CardKind, SourceTier


def _repository(tenant: str, user: str, content: str, *, kind: ContextKind) -> ContextRepository:
    namespace = ContextNamespace(tenant, user, "workspace")
    repository = ContextRepository(namespace, clock=lambda: 100.0)
    entry = ContextEntry(
        entry_id=f"entry-{tenant}-{user}-{kind.value}",
        namespace=namespace,
        key="shared-key",
        kind=kind,
        content=content,
        created_at=100.0,
        updated_at=100.0,
        confidence=0.95,
        salience=0.9,
        trust=0.98,
        source="test",
        tags=("canonical", kind.value),
        promoted=True,
    )
    patch = ContextPatch(
        patch_id=f"patch-{tenant}-{user}-{kind.value}",
        namespace=namespace,
        items=(ContextPatchItem(PatchOperation.UPSERT, entry.key, entry=entry),),
        author="test",
        created_at=100.0,
    )
    repository.commit("main", patch, message="seed canonical context", expected_head=None)
    return repository


def test_context_mesh_routes_session_to_workspace_without_cross_tenant_leakage() -> None:
    fabric = CognitiveContextFabric()
    mesh = ContextRepositoryMesh(fabric)
    left = _repository("tenant-a", "user-a", "private alpha diary memory", kind=ContextKind.DIARY)
    right = _repository("tenant-b", "user-b", "private beta diary secret", kind=ContextKind.DIARY)
    mesh.attach(left)
    mesh.attach(right)

    adapter = mesh.adapter(SourceTier.DIARY)
    canonical = adapter.fetch_refs(
        "tenant-a/user-a/workspace/session-1",
        ("shared-key",),
        max_records=4,
        max_tokens=1000,
    )
    assert len(canonical) == 1
    assert canonical[0].content == "private alpha diary memory"
    assert canonical[0].source_provider == "context-mesh:diary"

    fabric.index_record(
        "tenant-a/user-a/workspace/session-1",
        canonical[0],
        cue="alpha diary memory",
        kind=CardKind.EPISODE_CUE,
    )
    result = fabric.retrieve(
        "tenant-a/user-a/workspace/session-1",
        "alpha diary memory",
        requested_tiers=(SourceTier.DIARY,),
    )

    assert any(record.content == "private alpha diary memory" for record in result.records)
    assert all("beta diary secret" not in record.content for record in result.records)
    assert result.stale_card_ids == ()
    assert result.unresolved_source_refs == ()


def test_provider_identity_prevents_same_tier_same_ref_collision() -> None:
    fabric = CognitiveContextFabric()
    mesh = ContextRepositoryMesh(fabric)
    repository = _repository("tenant-a", "user-a", "user chronicle truth", kind=ContextKind.CHRONICLE)
    mesh.attach(repository)

    mesh_record = mesh.adapter(SourceTier.CHRONICLE).fetch_refs(
        repository.namespace.key,
        ("shared-key",),
        max_records=4,
        max_tokens=1000,
    )[0]
    card = fabric.index_record(
        repository.namespace.key,
        mesh_record,
        cue="chronicle collision",
        kind=CardKind.FACT_CUE,
    )

    def wrong_fetch(namespace_key, refs, max_records, max_tokens):
        if "shared-key" not in refs:
            return ()
        return (
            DeepContextRecord(
                source_tier=SourceTier.CHRONICLE,
                source_ref="shared-key",
                source_fingerprint="f" * 64,
                content="different provider with same ref",
                canonical=True,
                trust=1.0,
                confidence=1.0,
                salience=1.0,
                token_estimate=8,
                source_provider="scientific-lineage",
            ),
        )

    wrong = CallableContextAdapter(
        SourceTier.CHRONICLE,
        source_provider="scientific-lineage",
        fetcher=wrong_fetch,
        searcher=lambda namespace_key, query, max_records, max_tokens: (),
    )
    fabric.register(wrong)

    result = fabric.retrieve(
        repository.namespace.key,
        "chronicle collision",
        requested_tiers=(SourceTier.CHRONICLE,),
    )

    assert card.source_provider == "context-mesh:chronicle"
    assert card.card_id not in result.stale_card_ids
    assert any(record.content == "user chronicle truth" for record in result.records)
    assert all(record.content != "different provider with same ref" for record in result.records)


def test_explicit_durable_context_kinds_cover_requested_storage_classes() -> None:
    expected = {
        "journal",
        "log",
        "diary",
        "annal",
        "chronicle",
        "database",
        "cache",
        "file",
    }
    assert expected.issubset({kind.value for kind in ContextKind})
