from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from skeleton.contracts.memory_record import MemoryKind, MemoryWriteProposal
from skeleton.memory.core import CAGStore, InMemoryTFIDFStore, MAGStore
from skeleton.memory.projection import (
    CAGStoreProjection,
    LegacyMemoryStoreProjection,
    MAGStoreProjection,
    MemoryProjectionCoordinator,
    ProjectionState,
    TFIDFStoreProjection,
    VectorStoreProjection,
)
from skeleton.memory.vector import VectorStore
from skeleton.memory.store import MemoryStore
from skeleton.memory.types import MemoryChunk, MemoryQueryResult
from skeleton.persistence.memory_repository import SQLiteMemoryRepository


class FakeStore(MemoryStore):
    def __init__(self, *, fail_add: bool = False) -> None:
        self.items: dict[str, MemoryChunk] = {}
        self.fail_add = fail_add

    def add(self, chunk: MemoryChunk) -> None:
        if self.fail_add:
            raise RuntimeError("projection unavailable")
        self.items[chunk.id] = chunk

    def query(self, query_text, *, top_k=5, metadata_filter=None, min_score=0.0):
        return [
            MemoryQueryResult(chunk=item, score=1.0, rank=index + 1)
            for index, item in enumerate(self.items.values())
        ][:top_k]

    def delete(self, chunk_id: str) -> bool:
        return self.items.pop(chunk_id, None) is not None

    def health(self):
        return {"ok": not self.fail_add}


def _now():
    return datetime(2026, 9, 23, 17, 15, tzinfo=timezone.utc)


def _proposal(*, key: str, content: str, target=None, version=None):
    return MemoryWriteProposal(
        proposal_id=str(uuid4()),
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        kind=MemoryKind.SEMANTIC,
        idempotency_key=key,
        proposed_at=_now(),
        content=content,
        provenance_refs=("conversation:1",),
        source_operation_id=str(uuid4()),
        target_memory_id=target,
        expected_version=version,
    )


def test_projection_is_rebuildable_from_canonical_authority() -> None:
    repo = SQLiteMemoryRepository()
    one = repo.commit(_proposal(key="one", content="alpha"), now=_now())
    two = repo.commit(_proposal(key="two", content="beta"), now=_now())
    store = FakeStore()
    projection = LegacyMemoryStoreProjection("rag", store)
    coordinator = MemoryProjectionCoordinator(repo)

    report = coordinator.rebuild_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
        known_projection_ids=("stale-id",),
    )

    assert report.degraded is False
    assert set(store.items) == {one.memory_id, two.memory_id}
    assert store.items[one.memory_id].metadata["canonical_memory_id"] == one.memory_id
    assert store.items[one.memory_id].source_tier == "derived:rag"


def test_tombstone_deletes_projection_without_erasing_canonical_lineage() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(_proposal(key="one", content="alpha"), now=_now())
    store = FakeStore()
    projection = LegacyMemoryStoreProjection("rag", store)
    coordinator = MemoryProjectionCoordinator(repo)
    coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
    )
    assert record.memory_id in store.items

    tombstone = repo.tombstone(
        record.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=1,
        now=_now(),
    )
    report = coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
    )

    assert tombstone.memory_id not in store.items
    assert report.tombstones == 1
    exported = coordinator.export_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
    )
    assert exported[0]["state"] == "tombstoned"
    assert exported[0]["payload_digest"] == record.payload_digest


def test_projection_failure_is_degraded_not_authoritative_rollback() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(_proposal(key="one", content="alpha"), now=_now())
    healthy_store = FakeStore()
    failing_store = FakeStore(fail_add=True)
    coordinator = MemoryProjectionCoordinator(repo)

    report = coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(
            LegacyMemoryStoreProjection("rag", healthy_store),
            LegacyMemoryStoreProjection("mag", failing_store),
        ),
    )

    assert report.degraded is True
    assert report.results[0].state is ProjectionState.HEALTHY
    assert report.results[1].state is ProjectionState.DEGRADED
    assert report.results[1].error_code == "RuntimeError"
    assert record.memory_id in healthy_store.items
    canonical = repo.get(
        record.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
    )
    assert canonical.payload_digest == record.payload_digest


def test_export_ignores_projection_health_entirely() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(_proposal(key="one", content="alpha"), now=_now())
    coordinator = MemoryProjectionCoordinator(repo)

    exported = coordinator.export_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
    )

    assert exported == (record.as_dict(),)

def test_real_tfidf_and_vector_stores_rebuild_from_canonical_authority() -> None:
    repo = SQLiteMemoryRepository()
    one = repo.commit(_proposal(key="one-real", content="alpha memory"), now=_now())
    two = repo.commit(_proposal(key="two-real", content="beta memory"), now=_now())
    tfidf = InMemoryTFIDFStore()
    vector = VectorStore(dims=32)
    coordinator = MemoryProjectionCoordinator(repo)

    report = coordinator.rebuild_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(
            TFIDFStoreProjection("tfidf", tfidf),
            VectorStoreProjection("vector", vector),
        ),
        known_projection_ids=("stale-memory",),
    )

    assert report.degraded is False
    assert tfidf.stats()["documents"] == 2
    assert vector.stats()["documents"] == 2
    assert {result.chunk.chunk_id for result in tfidf.query("alpha", top_k=5)} == {one.memory_id}
    assert vector.query("beta", top_k=5)[0].chunk.chunk_id in {one.memory_id, two.memory_id}


def test_real_cag_and_mag_stores_delete_tombstoned_memory() -> None:
    repo = SQLiteMemoryRepository()
    record = repo.commit(_proposal(key="real-derived", content="remember real"), now=_now())
    cag = CAGStore()
    mag = MAGStore(agent_id="user-a")
    coordinator = MemoryProjectionCoordinator(repo)
    projections = (
        CAGStoreProjection("cag", cag),
        MAGStoreProjection("mag", mag),
    )

    initial = coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=projections,
    )
    assert initial.degraded is False
    assert cag.recall(record.memory_id)["text"] == "remember real"
    assert mag.stats()["episodes"] == 1

    repo.tombstone(
        record.memory_id,
        tenant_id="tenant-a",
        namespace="assistant",
        expected_version=1,
        now=_now(),
    )
    after = coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=projections,
    )

    assert after.tombstones == 1
    assert cag.recall(record.memory_id) is None
    assert mag.stats()["episodes"] == 0


def test_real_tfidf_upsert_replaces_prior_terms_without_counter_drift() -> None:
    repo = SQLiteMemoryRepository()
    first = repo.commit(_proposal(key="tf-one", content="alpha alpha"), now=_now())
    store = InMemoryTFIDFStore()
    projection = TFIDFStoreProjection("tfidf", store)
    coordinator = MemoryProjectionCoordinator(repo)

    coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
    )
    assert store.stats()["documents"] == 1

    repo.commit(
        _proposal(
            key="tf-two",
            content="beta beta",
            target=first.memory_id,
            version=1,
        ),
        now=_now(),
    )
    coordinator.sync_subject(
        tenant_id="tenant-a",
        namespace="assistant",
        subject_id="user-a",
        projections=(projection,),
    )

    assert store.stats()["documents"] == 1
    assert store.query("alpha", top_k=5) == []
    assert store.query("beta", top_k=5)[0].chunk.chunk_id == first.memory_id
